from __future__ import annotations

import logging
from dataclasses import dataclass
import httpx

from app.agent.order_status_agent import OrderStatusAgent, validate_order_status_reply
from app.apparel_magic.client_async import AsyncApparelMagicClient
from app.apparel_magic.models import Customer
from app.constants import LOG_SNIPPET_CHARS
from app.services.order_status_context import build_order_status_context
from app.settings import Settings
from app.shopify.admin_client_async import AsyncShopifyAdminClient
from app.zoho.desk.comment_html import plain_text_to_zoho_html
from app.zoho.desk.intent_classifier import TicketIntent

logger = logging.getLogger(__name__)


@dataclass
class OrderStatusRunResult:
    """Outcome of order-status automation."""

    public_html: str | None = None
    close_ticket: bool = False
    handoff_support: bool = False
    skipped: bool = False


async def run_order_status(
    *,
    ticket_id: str | None,
    subject: str,
    body: str,
    http: httpx.AsyncClient,
    settings: Settings,
    am: AsyncApparelMagicClient,
    requester_email: str,
    intent: TicketIntent,
    customer: Customer | None,
) -> OrderStatusRunResult:
    """
    Build summarized Shopify/AM context and run the order-status LLM agent.
    """
    extra_base: dict[str, object] = {
        "event": "order_status",
        "ticket_id": ticket_id or "",
    }
    shopify = AsyncShopifyAdminClient(http, settings)
    shopify_client: AsyncShopifyAdminClient | None = shopify if shopify.configured() else None

    try:
        ctx = await build_order_status_context(
            am=am,
            shopify=shopify_client,
            requester_email=requester_email,
            intent_email=intent.email,
            customer=customer,
            intent_order_id=intent.order_id,
        )
    except Exception:
        logger.exception("order_status_context_failed", extra=extra_base)
        return OrderStatusRunResult()

    if ctx is None:
        logger.info("order_status_skipped_no_context ticket_id=%s", ticket_id or "", extra=extra_base)
        return OrderStatusRunResult(skipped=True)

    try:
        agent = OrderStatusAgent(http, settings)
        raw = await agent.run(subject, body, ctx)
    except Exception:
        logger.exception("order_status_agent_failed", extra=extra_base)
        return OrderStatusRunResult()

    ticket_ctx = (f"{subject}\n{body}").strip()[:LOG_SNIPPET_CHARS]
    reply = validate_order_status_reply(raw)
    logger.debug(
        "order_status_model_output ticket_id=%s post_reply=%s close=%s handoff=%s snippet=%r",
        ticket_id or "",
        reply.post_reply,
        reply.close_ticket,
        reply.handoff_support,
        ticket_ctx,
        extra=extra_base,
    )

    if reply.handoff_support:
        logger.info(
            "order_status_handoff ticket_id=%s posted_brief=%s ticket_context_snippet=%r",
            ticket_id or "",
            bool(reply.post_reply and reply.reply_plain),
            ticket_ctx,
            extra={**extra_base, "handoff": True},
        )
        if reply.post_reply and reply.reply_plain:
            html = plain_text_to_zoho_html(reply.reply_plain)
            return OrderStatusRunResult(
                public_html=html,
                close_ticket=False,
                handoff_support=True,
            )
        return OrderStatusRunResult(handoff_support=True)

    if not reply.post_reply or not reply.reply_plain:
        logger.info(
            "order_status_no_public_reply ticket_id=%s ticket_context_snippet=%r",
            ticket_id or "",
            ticket_ctx,
            extra=extra_base,
        )
        return OrderStatusRunResult()

    html = plain_text_to_zoho_html(reply.reply_plain)
    preview = reply.reply_plain[:LOG_SNIPPET_CHARS]
    logger.info(
        "order_status_public_reply ticket_id=%s close_ticket=%s reply_preview=%r",
        ticket_id or "",
        reply.close_ticket,
        preview,
        extra={**extra_base, "post_reply": True, "close_ticket": reply.close_ticket},
    )
    return OrderStatusRunResult(
        public_html=html,
        close_ticket=reply.close_ticket,
        handoff_support=False,
    )
