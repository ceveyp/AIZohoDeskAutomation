from __future__ import annotations

import logging
from typing import Any

import httpx

from app.agent.product_inquiry_agent import ProductInquiryAgent, validate_reply
from app.constants import LOG_SNIPPET_CHARS
from app.settings import Settings
from app.zoho.desk.comment_html import plain_text_to_zoho_html

logger = logging.getLogger(__name__)


async def run_product_inquiry(
    *,
    ticket_id: str | None,
    subject: str,
    body: str,
    http: httpx.AsyncClient,
    settings: Settings,
) -> str | None:
    """
    Run the product-inquiry agent. Returns HTML for a Zoho public comment, or None to stay silent.
    """
    extra_base: dict[str, Any] = {
        "event": "product_inquiry",
        "ticket_id": ticket_id or "",
    }
    try:
        agent = ProductInquiryAgent(http, settings)
        raw = await agent.run(subject, body)
        ticket_ctx = (f"{subject}\n{body}").strip()[:LOG_SNIPPET_CHARS]
        logger.debug(
            "product_inquiry_model_output ticket_id=%s post_reply=%s reply_plain_len=%s",
            ticket_id or "",
            raw.post_reply,
            len((raw.reply_plain or "")),
        )
        reply = validate_reply(raw)
        if not reply.post_reply or not reply.reply_plain:
            logger.info(
                "product_inquiry_no_public_reply ticket_id=%s raw_post_reply=%s raw_reply_plain_len=%s "
                "validated_post_reply=%s validated_reply_plain_len=%s ticket_context_snippet=%r "
                "raw_reply_plain_preview=%r (check internal_inventory_search_catalog_response raw_count vs "
                "returned_count if PRODUCT_SEARCH_MIN_* filters empty results)",
                ticket_id or "",
                raw.post_reply,
                len((raw.reply_plain or "")),
                reply.post_reply,
                len((reply.reply_plain or "")),
                ticket_ctx,
                (raw.reply_plain or "")[:LOG_SNIPPET_CHARS],
                extra={**extra_base, "post_reply": False},
            )
            return None
        preview = (reply.reply_plain or "")[:LOG_SNIPPET_CHARS]
        logger.info(
            "product_inquiry_public_reply ticket_id=%s reply_chars=%s reply_preview=%r",
            ticket_id or "",
            len(reply.reply_plain),
            preview,
            extra={
                **extra_base,
                "post_reply": True,
                "reply_chars": len(reply.reply_plain),
            },
        )
        return plain_text_to_zoho_html(reply.reply_plain)
    except Exception:
        logger.exception(
            "product_inquiry_failed",
            extra=extra_base,
        )
        return None
