from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import re
from typing import Any

import httpx
import trafilatura

from app.apparel_magic.client_async import AsyncApparelMagicClient
from app.apparel_magic.models import Customer
from app.constants import LOG_SNIPPET_CHARS
from app.settings import Settings
from app.zoho.desk.client_async import AsyncZohoDeskClient
from app.services.order_status_runner import run_order_status
from app.services.product_inquiry_runner import run_product_inquiry
from app.services.zoho_assignee import resolve_zoho_assignee_for_customer
from app.zoho.desk.intent_classifier import IntentClassifier

logger = logging.getLogger(__name__)

# Large Zoho payloads (chat HTML) are logged in chunks to avoid single-line limits.
_LOG_JSON_CHUNK_SIZE = 24_000

SHOPIFY_MAILER_EMAIL = "mailer@shopify.com"
PROCESSED_TICKET_EVENTS = frozenset({"Ticket_Add", "Ticket_Update"})

# Product inquiry is limited to this department unless Settings.product_inquiry_all_departments is true.
_PRODUCT_INQUIRY_DEPARTMENT_ID_IT = "1125678000004960029"


def _log_json_chunks(prefix: str, obj: Any, *, level: int = logging.DEBUG) -> None:
    """Serialize ``obj`` to JSON and log in chunks (handles huge chat transcripts)."""
    try:
        serialized = json.dumps(obj, default=str)
    except Exception as exc:
        logger.log(level, "%s json.dumps failed: %s", prefix, exc)
        return
    n = len(serialized)
    if n <= _LOG_JSON_CHUNK_SIZE:
        logger.log(level, "%s len=%d %s", prefix, n, serialized)
        return
    total_chunks = (n + _LOG_JSON_CHUNK_SIZE - 1) // _LOG_JSON_CHUNK_SIZE
    logger.log(level, "%s len=%d chunks=%d", prefix, n, total_chunks)
    for start in range(0, n, _LOG_JSON_CHUNK_SIZE):
        part = start // _LOG_JSON_CHUNK_SIZE + 1
        logger.log(
            level,
            "%s chunk %d/%d %s",
            prefix,
            part,
            total_chunks,
            serialized[start : start + _LOG_JSON_CHUNK_SIZE],
        )


def _first_thread_diagnostics(ticket: dict[str, Any]) -> dict[str, Any]:
    ft = ticket.get("firstThread")
    if not isinstance(ft, dict):
        return {"firstThread": None}
    content = ft.get("content")
    raw = content if isinstance(content, str) else ""
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]
    return {
        "firstThread_id": ft.get("id"),
        "firstThread_content_len": len(raw),
        "firstThread_content_sha256_16": digest,
        "firstThread_keys": sorted(ft.keys()),
    }


def normalize_events(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def _department_allows_product_inquiry(payload: dict[str, Any], settings: Settings) -> bool:
    if settings.product_inquiry_all_departments:
        return True
    dept = str(payload.get("departmentId") or "").strip()
    return dept == _PRODUCT_INQUIRY_DEPARTMENT_ID_IT


def _resolve_requester_email(payload: dict[str, Any]) -> str | None:
    email = payload.get("email")
    if isinstance(email, str) and email.strip():
        return email.strip()
    contact = payload.get("contact") or {}
    if isinstance(contact, dict):
        ce = contact.get("email")
        if isinstance(ce, str) and ce.strip():
            return ce.strip()
    return None


def _strip_html_to_plain(fragment: str) -> str:
    """Remove tags and decode entities when trafilatura yields nothing (e.g. short Zoho Desk markup)."""
    text = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        fragment,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def _html_to_text(html_fragment: str | None) -> str:
    if not html_fragment:
        return ""
    extracted = await asyncio.to_thread(trafilatura.extract, html_fragment)
    text = (extracted or "").strip()
    if text:
        return text
    fallback = _strip_html_to_plain(html_fragment)
    if fallback:
        logger.debug(
            "trafilatura returned empty description; HTML strip fallback len=%d preview=%r",
            len(fallback),
            fallback[:LOG_SNIPPET_CHARS],
        )
    return fallback


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


async def _ticket_dict_to_body_plain(ticket: dict[str, Any]) -> str:
    """
    Plain text from ticket description plus first thread (e.g. chat transcript).
    Used for LLM input and for Ticket_Update change detection.
    """
    parts: list[str] = []
    desc = ticket.get("description")
    if isinstance(desc, str) and desc.strip():
        parts.append(await _html_to_text(desc))
    first = ticket.get("firstThread")
    if isinstance(first, dict):
        content = first.get("content")
        if isinstance(content, str) and content.strip():
            parts.append(await _html_to_text(content))
    return "\n\n".join(p.strip() for p in parts if p.strip()).strip()


async def _maybe_assign_ticket_from_am_salesperson(
    zoho: AsyncZohoDeskClient,
    am: AsyncApparelMagicClient,
    ticket_id: str,
    customer: Customer,
) -> None:
    assignee = await resolve_zoho_assignee_for_customer(am, zoho, customer)
    if assignee and assignee.assignee_id:
        try:
            await zoho.update_ticket_assignee(ticket_id, assignee.assignee_id)
            logger.info(
                "Assigned ticket %s to Zoho agent id=%s name=%r email=%r (AM salesperson name=%r id=%r reason=%s)",
                ticket_id,
                assignee.assignee_id,
                assignee.name,
                assignee.email,
                assignee.am_salesperson_name,
                assignee.am_salesperson_id,
                assignee.reason,
            )
        except Exception:
            logger.exception(
                "Failed assigning ticket %s from AM salesperson name=%r id=%r",
                ticket_id,
                assignee.am_salesperson_name,
                assignee.am_salesperson_id,
            )
    else:
        logger.info(
            "No salesperson->Zoho assignee match for ticket %s customer_id=%s",
            ticket_id,
            customer.customer_id,
        )


async def process_ticket_add_payload(
    payload: dict[str, Any],
    zoho: AsyncZohoDeskClient,
    am: AsyncApparelMagicClient,
    classifier: IntentClassifier,
    http: httpx.AsyncClient,
    settings: Settings,
    *,
    event_type: str = "Ticket_Add",
    prev_state: dict[str, Any] | None = None,
) -> None:
    ticket_id = str(payload.get("id") or "")
    if not ticket_id:
        logger.warning("Ticket webhook payload missing id (event_type=%s)", event_type)
        return

    if payload.get("isSpam") or payload.get("isArchived") or payload.get("isTrashed"):
        logger.info("Skipping ticket %s (spam/archived/trashed)", ticket_id)
        return

    if (payload.get("status") or "") != "Open":
        logger.info("Skipping ticket %s (status not Open)", ticket_id)
        return

    requester_email = _resolve_requester_email(payload)
    if not requester_email:
        logger.info("No requester email on ticket %s", ticket_id)
        return

    if requester_email.lower() == SHOPIFY_MAILER_EMAIL:
        logger.debug("Skipping Shopify mailer ticket %s", ticket_id)
        return

    if event_type == "Ticket_Update" and isinstance(prev_state, dict):
        desc_p = payload.get("description")
        desc_prev = prev_state.get("description")
        desc_p_len = len(desc_p) if isinstance(desc_p, str) else 0
        desc_prev_len = len(desc_prev) if isinstance(desc_prev, str) else 0
        diag_p = _first_thread_diagnostics(payload)
        diag_prev = _first_thread_diagnostics(prev_state)
        logger.info(
            "Ticket_Update compare ticket_id=%s payload_modifiedTime=%r prev_modifiedTime=%r "
            "payload_assigneeId=%r prev_assigneeId=%r desc_len_payload=%s desc_len_prev=%s "
            "firstThread_diag_payload=%s firstThread_diag_prev=%s",
            ticket_id,
            payload.get("modifiedTime"),
            prev_state.get("modifiedTime"),
            payload.get("assigneeId"),
            prev_state.get("assigneeId"),
            desc_p_len,
            desc_prev_len,
            diag_p,
            diag_prev,
        )
        body_cur = await _ticket_dict_to_body_plain(payload)
        body_prev = await _ticket_dict_to_body_plain(prev_state)
        norm_cur = _normalize_ws(body_cur)
        norm_prev = _normalize_ws(body_prev)
        logger.info(
            "Ticket_Update body_plain ticket_id=%s cur_len=%d prev_len=%d norm_equal=%s "
            "cur_norm_sha16=%s prev_norm_sha16=%s cur_preview=%r prev_preview=%r",
            ticket_id,
            len(body_cur),
            len(body_prev),
            norm_cur == norm_prev,
            hashlib.sha256(norm_cur.encode("utf-8", errors="replace")).hexdigest()[:16],
            hashlib.sha256(norm_prev.encode("utf-8", errors="replace")).hexdigest()[:16],
            body_cur[:LOG_SNIPPET_CHARS],
            body_prev[:LOG_SNIPPET_CHARS],
        )
        if norm_cur == norm_prev:
            logger.info(
                "Ticket_Update unchanged content check disabled for testing; continuing ticket_id=%s",
                ticket_id,
            )

    subject = str(payload.get("subject") or "")
    body_plain = await _ticket_dict_to_body_plain(payload)
    body_for_llm = f"{subject}\n\n{body_plain}".strip()
    logger.info(
        "ticket_webhook processing ticket_id=%s event_type=%s subject_len=%d body_plain_len=%d "
        "body_for_llm_len=%d departmentId=%r channel=%r status=%r",
        ticket_id,
        event_type,
        len(subject),
        len(body_plain),
        len(body_for_llm),
        payload.get("departmentId"),
        payload.get("channel"),
        payload.get("status"),
    )
    logger.debug(
        "ticket_webhook body_for_llm preview ticket_id=%s preview=%r",
        ticket_id,
        body_for_llm[:LOG_SNIPPET_CHARS],
    )

    intent = await classifier.classify_async(subject, body_for_llm or subject)

    customer: Customer | None = await am.get_customer_by_email(requester_email)
    if customer and customer.customer_id:
        contact_email = (intent.email or requester_email).strip()
        if contact_email.lower() != requester_email.lower():
            alt = await am.get_customer_by_email(contact_email)
            if alt and alt.customer_id:
                customer = alt
        await _maybe_assign_ticket_from_am_salesperson(zoho, am, ticket_id, customer)

    if intent.intent == "support":
        _body_snip = (body_for_llm or "")[:LOG_SNIPPET_CHARS]
        logger.info(
            "Ticket %s intent=%s; not auto-handling subject=%r body_prefix=%r",
            ticket_id,
            intent.intent,
            subject[:LOG_SNIPPET_CHARS],
            _body_snip,
        )
        return

    if intent.intent == "product_inquiry":
        if not _department_allows_product_inquiry(payload, settings):
            logger.info(
                "Skipping product_inquiry for ticket %s (departmentId=%r; "
                "allowed only for IT department unless PRODUCT_INQUIRY_ALL_DEPARTMENTS=true)",
                ticket_id,
                payload.get("departmentId"),
            )
            return
        comment_html = await run_product_inquiry(
            ticket_id=ticket_id,
            subject=subject,
            body=body_for_llm or subject,
            http=http,
            settings=settings,
        )
        if comment_html:
            await zoho.add_public_comment(ticket_id, comment_html)
            logger.info("Posted product-inquiry comment on ticket %s", ticket_id)
        else:
            logger.info(
                "Product-inquiry produced no public comment for ticket %s context_snippet=%r",
                ticket_id,
                (body_for_llm or "")[:LOG_SNIPPET_CHARS],
            )
        return

    if intent.intent != "order_status":
        logger.info("Ticket %s intent=%s; not auto-handling", ticket_id, intent.intent)
        return

    os_result = await run_order_status(
        ticket_id=ticket_id,
        subject=subject,
        body=body_for_llm or subject,
        http=http,
        settings=settings,
        am=am,
        requester_email=requester_email,
        intent=intent,
        customer=customer,
    )
    if os_result.skipped:
        logger.info(
            "Order-status noop (no Shopify/AM context) ticket %s email=%s",
            ticket_id,
            requester_email,
        )
        return
    if os_result.public_html:
        await zoho.add_public_comment(ticket_id, os_result.public_html)
        logger.info(
            "Posted order-status comment on ticket %s handoff=%s",
            ticket_id,
            os_result.handoff_support,
        )
    if os_result.close_ticket:
        await zoho.update_ticket_status(ticket_id, "Closed")
        logger.info("Closed order-status ticket %s", ticket_id)
    elif os_result.handoff_support and not os_result.public_html:
        logger.info("Order-status handoff (no public reply) ticket %s", ticket_id)


async def _handle_one_event(
    event: dict[str, Any],
    zoho: AsyncZohoDeskClient,
    am: AsyncApparelMagicClient,
    classifier: IntentClassifier,
    http: httpx.AsyncClient,
    settings: Settings,
) -> None:
    event_type_raw = event.get("eventType")
    org_id_raw = event.get("orgId")
    logger.info(
        "zoho_webhook event received eventType=%r orgId=%r orgId_type=%s event_keys=%s",
        event_type_raw,
        org_id_raw,
        type(org_id_raw).__name__,
        sorted(event.keys()) if isinstance(event, dict) else None,
    )
    _log_json_chunks("zoho_webhook full event JSON", event, level=logging.INFO)

    org_id = str(event.get("orgId") or "")
    if org_id != settings.zoho_org_id:
        logger.warning(
            "Ignoring event for orgId=%r str_orgId=%r (expected %s) eventType=%r",
            org_id_raw,
            org_id,
            settings.zoho_org_id,
            event_type_raw,
        )
        return

    event_type = event.get("eventType")
    if event_type not in PROCESSED_TICKET_EVENTS:
        logger.debug("Skipping event type %s", event_type)
        return

    payload = event.get("payload")
    if not isinstance(payload, dict):
        logger.warning("Event missing payload dict")
        return

    ticket_id_dbg = str(payload.get("id") or "")
    logger.info(
        "zoho_webhook accepted eventType=%s ticket_id=%s has_prevState=%s",
        event_type,
        ticket_id_dbg,
        isinstance(event.get("prevState"), dict),
    )
    _log_json_chunks(
        f"zoho_webhook full payload JSON ticket_id={ticket_id_dbg or 'unknown'}",
        payload,
        level=logging.INFO,
    )
    prev = event.get("prevState")
    if isinstance(prev, dict):
        _log_json_chunks(
            f"zoho_webhook full prevState JSON ticket_id={ticket_id_dbg or 'unknown'}",
            prev,
            level=logging.INFO,
        )
    prev_state = prev if isinstance(prev, dict) else None
    await process_ticket_add_payload(
        payload,
        zoho,
        am,
        classifier,
        http,
        settings,
        event_type=str(event_type or "Ticket_Add"),
        prev_state=prev_state,
    )


async def process_zoho_webhook_events(
    raw: Any,
    http: httpx.AsyncClient,
    settings: Settings,
) -> None:
    logger.debug(
        "zoho_webhook raw body type=%s len=%s",
        type(raw).__name__,
        len(raw) if isinstance(raw, (str, bytes)) else None,
    )
    _log_json_chunks("zoho_webhook raw request body JSON", raw, level=logging.INFO)
    events = normalize_events(raw)
    if not events:
        logger.info("Webhook received empty or unrecognized body")
        return
    logger.info("zoho_webhook normalized event count=%d", len(events))

    zoho = AsyncZohoDeskClient(http, settings)
    am = AsyncApparelMagicClient(http, settings)
    classifier = IntentClassifier()

    for event in events:
        try:
            await _handle_one_event(event, zoho, am, classifier, http, settings)
        except Exception:
            logger.exception("Failed processing webhook event")
