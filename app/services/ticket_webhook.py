from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import Any

import httpx
import trafilatura

from app.apparel_magic.client_async import AsyncApparelMagicClient
from app.apparel_magic.models import Order, OrderItem
from app.constants import LOG_SNIPPET_CHARS
from app.settings import Settings
from app.zoho.desk.client_async import AsyncZohoDeskClient
from app.zoho.desk.comment_html import plain_text_to_zoho_html
from app.services.product_inquiry_runner import run_product_inquiry
from app.services.zoho_assignee import resolve_zoho_assignee_for_customer
from app.zoho.desk.intent_classifier import IntentClassifier

logger = logging.getLogger(__name__)

SHOPIFY_MAILER_EMAIL = "mailer@shopify.com"
PROCESSED_TICKET_EVENTS = frozenset({"Ticket_Add"})
MAX_ORDERS_IN_REPLY = 50

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


def _sort_orders_newest_first(orders: list[Order]) -> list[Order]:
    return sorted(orders, key=lambda o: o.date or "", reverse=True)


def _fmt_money(amount: float | int | None) -> str:
    if amount is None:
        return "—"
    try:
        return f"${float(amount):,.2f}"
    except (TypeError, ValueError):
        return str(amount)


def _line_sku(line: OrderItem) -> str:
    if line.sku_alt:
        return line.sku_alt
    if line.style_number and line.attr_2 and line.size:
        return f"{line.style_number} / {line.attr_2} / {line.size}"
    return line.sku_id or line.style_number or "—"


def _format_line_item_html(line: OrderItem, index: int, currency: str) -> str:
    desc = line.description or "Product"
    cur = f" {currency}" if currency else ""
    cur_suffix = f" {currency}" if currency else ""
    parts = [
        f"Item {index}: {desc}",
        f"SKU: {_line_sku(line)}",
        f"Size: {line.size or '—'}",
        f"Color: {line.attr_2 or '—'}",
        f"Qty: {line.qty or '0'}",
        f"Line amount: {_fmt_money(line.amount)}{cur_suffix}",
    ]
    if line.qty_open is not None or line.qty_shipped is not None:
        parts.append(
            f"Qty open / shipped: {line.qty_open or '0'} / {line.qty_shipped or '0'}"
        )
    if line.date_due:
        parts.append(f"Ship by: {line.date_due}")
    inner = "<br />".join(html.escape(p) for p in parts)
    return f"<p>{inner}</p>"


def _format_one_order_html(o: Order) -> str:
    cur = o.currency_name or ""
    oid = html.escape(str(o.order_id or "N/A"))
    header_lines = [
        f"Order date: {o.date or '—'}",
        f"Due date: {o.date_due or '—'}",
    ]
    if o.date_start:
        header_lines.append(f"Start date: {o.date_start}")
    if o.last_modified_time:
        header_lines.append(f"Last updated: {o.last_modified_time}")
    header_lines.extend(
        [
            f"Overall fulfillment: {o.fulfillment_status or '—'}",
            f"WMS status: {o.wms_status or '—'}",
            f"Order qty (open / shipped): {o.qty_open or '0'} / {o.qty_shipped or '0'}",
        ]
    )
    if o.ship_via:
        header_lines.append(f"Ship via: {o.ship_via}")
    if o.balance is not None:
        header_lines.append(f"Balance: {_fmt_money(o.balance)}{(' ' + cur) if cur else ''}")

    header_inner = "<br />".join(html.escape(x) for x in header_lines)
    blocks = [f"<p><b>Order {oid}</b><br />{header_inner}</p>"]

    items = o.order_items or []
    if items:
        blocks.append("<p><b>" + html.escape("Items") + "</b></p>")
        for i, line in enumerate(items, start=1):
            blocks.append(_format_line_item_html(line, i, cur))
    else:
        blocks.append(
            "<p>"
            + html.escape("No line items were returned for this order.")
            + "</p>"
        )

    return "".join(blocks)


def _build_order_status_html(orders: list[Order]) -> str:
    """HTML body for Zoho Desk public comments (renders line breaks in UI and email)."""
    if not orders:
        return (
            "<p>"
            + html.escape(
                "Thank you for contacting Gameday Social. We could not find any orders "
                "for your account in our system."
            )
            + "</p>"
        )
    header = (
        "<p>"
        + html.escape(
            "Thank you for contacting Gameday Social. Here is the status we have on file:"
        )
        + "</p>"
    )
    blocks = [_format_one_order_html(o) for o in orders[:MAX_ORDERS_IN_REPLY]]
    body = "<hr />".join(blocks)
    if len(orders) > MAX_ORDERS_IN_REPLY:
        body += (
            "<p>"
            + html.escape(f"(Showing first {MAX_ORDERS_IN_REPLY} orders.)")
            + "</p>"
        )
    return header + body


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

    customer = await am.get_customer_by_email(requester_email)
    if not customer or not customer.customer_id:
        logger.info("No Apparel Magic customer for %s; skipping automation", requester_email)
        return

    contact_email = (intent.email or requester_email).strip()
    if contact_email.lower() != requester_email.lower():
        alt = await am.get_customer_by_email(contact_email)
        if alt and alt.customer_id:
            customer = alt

    if intent.intent != "order_status":
        logger.info("Ticket %s intent=%s; not auto-handling", ticket_id, intent.intent)
        return

    assignee = await resolve_zoho_assignee_for_customer(zoho, customer)
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

    oid = (intent.order_id or "").strip()

    if oid:
        order = await am.get_order_by_id(oid)
        if not order:
            logger.info(
                "Order %s not found in AM for ticket %s; leaving ticket for support",
                oid,
                ticket_id,
            )
            return
        if (
            order.customer_id
            and customer.customer_id
            and str(order.customer_id) != str(customer.customer_id)
        ):
            msg = plain_text_to_zoho_html(
                "Thank you for contacting Gameday Social. We could not match that order "
                "to your account. If you believe this is an error, please reply with "
                "the email address used on the order."
            )
        else:
            msg = _build_order_status_html([order])
    else:
        all_orders = await am.get_orders_by_customer_id(str(customer.customer_id))
        orders_out = _sort_orders_newest_first(all_orders)
        msg = _build_order_status_html(orders_out)

    await zoho.add_public_comment(ticket_id, msg)
    await zoho.update_ticket_status(ticket_id, "Closed")
    logger.info("Processed order-status ticket %s", ticket_id)


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
