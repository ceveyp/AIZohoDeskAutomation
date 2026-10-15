from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from app.agent.ticket_tagging_agent import TicketTaggingAgent
from app.settings import Settings
from app.zoho.desk.client_async import AsyncZohoDeskClient

logger = logging.getLogger(__name__)

_TAG_LINE_RE = re.compile(r'^\s*"(?P<tag>[^"]+)"\s*[—-]\s*(?P<description>.+?)\s*$')


@dataclass
class TicketTaggingResult:
    tags: list[str]
    uncertain: bool
    uncertain_reason: str | None


@lru_cache(maxsize=1)
def load_tag_definitions() -> list[dict[str, str]]:
    root = Path(__file__).resolve().parent.parent.parent
    tags_file = root / "tags.txt"
    rows: list[dict[str, str]] = []
    for line in tags_file.read_text(encoding="utf-8").splitlines():
        m = _TAG_LINE_RE.match(line)
        if not m:
            continue
        tag = m.group("tag").strip()
        desc = m.group("description").strip()
        if tag:
            rows.append({"tag": tag, "description": desc})
    if not rows:
        raise RuntimeError(f"No tags parsed from {tags_file}")
    return rows


def _extract_most_recent_message(payload: dict[str, Any], body_fallback: str) -> str:
    first = payload.get("firstThread")
    if isinstance(first, dict):
        content = first.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return body_fallback


async def predict_ticket_tags(
    *,
    subject: str,
    body: str,
    payload: dict[str, Any],
    http: httpx.AsyncClient,
    settings: Settings,
) -> TicketTaggingResult:
    defs = load_tag_definitions()
    agent = TicketTaggingAgent(http, defs, settings)
    metadata = {
        "ticket_id": str(payload.get("id") or ""),
        "ticket_number": payload.get("ticketNumber"),
        "channel": payload.get("channel"),
        "department_id": payload.get("departmentId"),
        "status": payload.get("status"),
        "priority": payload.get("priority"),
        "email": payload.get("email"),
        "contact_email": (payload.get("contact") or {}).get("email")
        if isinstance(payload.get("contact"), dict)
        else None,
    }
    most_recent = _extract_most_recent_message(payload, body)
    reply = await agent.run(
        subject=subject,
        body=body,
        most_recent_message=most_recent,
        metadata=metadata,
    )
    return TicketTaggingResult(
        tags=reply.tags,
        uncertain=reply.uncertain,
        uncertain_reason=reply.uncertain_reason,
    )


async def tag_ticket(
    *,
    ticket_id: str,
    subject: str,
    body: str,
    payload: dict[str, Any],
    zoho: AsyncZohoDeskClient,
    http: httpx.AsyncClient,
    settings: Settings,
) -> TicketTaggingResult:
    result = await predict_ticket_tags(
        subject=subject,
        body=body,
        payload=payload,
        http=http,
        settings=settings,
    )
    logger.info(
        "ticket_tagging_decision ticket_id=%s tags=%s uncertain=%s reason=%r",
        ticket_id,
        result.tags,
        result.uncertain,
        result.uncertain_reason,
    )
    if not result.tags:
        return result
    try:
        await zoho.associate_tags(ticket_id, result.tags)
        logger.info("ticket_tagging_associated ticket_id=%s tags=%s", ticket_id, result.tags)
    except Exception:
        logger.exception("ticket_tagging_associate_failed ticket_id=%s tags=%s", ticket_id, result.tags)
    return result
