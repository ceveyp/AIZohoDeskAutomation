from __future__ import annotations

import logging
from typing import Any

import httpx

from app.agent.product_inquiry_agent import ProductInquiryAgent, validate_reply
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
        reply = validate_reply(raw)
        if not reply.post_reply or not reply.reply_plain:
            logger.info(
                "product_inquiry_no_public_reply",
                extra={**extra_base, "post_reply": False},
            )
            return None
        logger.info(
            "product_inquiry_public_reply",
            extra={**extra_base, "post_reply": True, "reply_chars": len(reply.reply_plain)},
        )
        return plain_text_to_zoho_html(reply.reply_plain)
    except Exception:
        logger.exception(
            "product_inquiry_failed",
            extra=extra_base,
        )
        return None
