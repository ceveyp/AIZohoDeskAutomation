from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.constants import SupportedModels
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class TicketTaggingReply(BaseModel):
    tags: list[str] = Field(default_factory=list)
    uncertain: bool = Field(default=False)
    uncertain_reason: str | None = Field(default=None)


def _build_instructions(tag_definitions: list[dict[str, str]]) -> str:
    tag_lines = "\n".join(
        f'- "{row["tag"]}" — {row["description"]}'
        for row in tag_definitions
    )
    return f"""
You assign Zoho Desk ticket tags.

## Allowed tags
Use only these exact tag strings:
{tag_lines}

## Inputs
You receive:
- Subject
- Full ticket body/context
- Most recent message
- Ticket metadata (channel, department, requester, etc.)

## Rules
- Return 0..5 tags from the allowed list only.
- Use multiple tags when clearly applicable.
- If the ticket appears junk/unsolicited/scam, include "spam".
- If uncertain, set uncertain=true and provide uncertain_reason.
- Never invent new tags.
- Be conservative: prefer fewer tags over speculative tags.
""".strip()


def validate_ticket_tagging_reply(
    raw: TicketTaggingReply,
    *,
    allowed_tags: set[str],
) -> TicketTaggingReply:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in raw.tags:
        t = (tag or "").strip()
        if not t or t not in allowed_tags or t in seen:
            continue
        seen.add(t)
        normalized.append(t)
    uncertain_reason = (raw.uncertain_reason or "").strip() or None
    return TicketTaggingReply(
        tags=normalized,
        uncertain=bool(raw.uncertain),
        uncertain_reason=uncertain_reason,
    )


class TicketTaggingAgent:
    def __init__(
        self,
        http: httpx.AsyncClient,
        tag_definitions: list[dict[str, str]],
        settings: Settings | None = None,
        *,
        model: SupportedModels = SupportedModels.GPT_5_MINI,
        recursion_limit: int = 20,
    ) -> None:
        _ = http  # Reserved for parity with other agents.
        settings = settings or get_settings()
        self._recursion_limit = recursion_limit
        self._allowed_tags = {row["tag"] for row in tag_definitions}
        llm = ChatOpenAI(
            model=model.value,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            max_retries=3,
            timeout=120.0,
        )
        self._agent = create_agent(
            model=llm,
            tools=[],
            response_format=TicketTaggingReply,
            system_prompt=_build_instructions(tag_definitions),
        )

    async def run(
        self,
        *,
        subject: str,
        body: str,
        most_recent_message: str,
        metadata: dict[str, Any],
    ) -> TicketTaggingReply:
        payload = {
            "subject": subject,
            "body": body,
            "most_recent_message": most_recent_message,
            "metadata": metadata,
        }
        prompt = f"Assign tags for this ticket:\n{json.dumps(payload, indent=2, default=str)}"
        result = await self._agent.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]},
            config={"recursion_limit": self._recursion_limit},
        )
        raw = result["structured_response"]
        return validate_ticket_tagging_reply(raw, allowed_tags=self._allowed_tags)
