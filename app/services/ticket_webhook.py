from __future__ import annotations

import asyncio
import html
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

SHOPIFY_MAILER_EMAIL = "mailer@shopify.com"
PROCESSED_TICKET_EVENTS = frozenset({"Ticket_Add"})

# TODO: remove — QA only. Product inquiry runs only for this Zoho Desk departmentId (webhook payload).
_PRODUCT_INQUIRY_DEPARTMENT_ID_IT = "1125678000004960029"


def normalize_events(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def _department_allows_product_inquiry(payload: dict[str, Any]) -> bool:
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
) -> None:
    ticket_id = str(payload.get("id") or "")
    if not ticket_id:
        logger.warning("Ticket_Add payload missing id")
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

    subject = str(payload.get("subject") or "")
    description_html = payload.get("description")
    description_text = await _html_to_text(
        description_html if isinstance(description_html, str) else None
    )
    body_for_llm = f"{subject}\n\n{description_text}".strip()

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
        if not _department_allows_product_inquiry(payload):
            logger.info(
                "Skipping product_inquiry for ticket %s (departmentId=%r; QA gate: IT only)",
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
    org_id = str(event.get("orgId") or "")
    if org_id != settings.zoho_org_id:
        logger.warning("Ignoring event for orgId=%s (expected %s)", org_id, settings.zoho_org_id)
        return

    event_type = event.get("eventType")
    if event_type not in PROCESSED_TICKET_EVENTS:
        logger.debug("Skipping event type %s", event_type)
        return

    payload = event.get("payload")
    if not isinstance(payload, dict):
        logger.warning("Event missing payload dict")
        return

    await process_ticket_add_payload(payload, zoho, am, classifier, http, settings)


async def process_zoho_webhook_events(
    raw: Any,
    http: httpx.AsyncClient,
    settings: Settings,
) -> None:
    events = normalize_events(raw)
    if not events:
        logger.info("Webhook received empty or unrecognized body")
        return

    zoho = AsyncZohoDeskClient(http, settings)
    am = AsyncApparelMagicClient(http, settings)
    classifier = IntentClassifier()

    for event in events:
        try:
            await _handle_one_event(event, zoho, am, classifier, http, settings)
        except Exception:
            logger.exception("Failed processing webhook event")
