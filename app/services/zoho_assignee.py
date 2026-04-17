from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.apparel_magic.client_async import AsyncApparelMagicClient
from app.apparel_magic.models import Customer
from app.zoho.desk.client_async import AsyncZohoDeskClient

logger = logging.getLogger(__name__)


@dataclass
class ZohoAssigneeMatch:
    assignee_id: str
    name: str
    email: str
    reason: str
    am_salesperson_name: str
    am_salesperson_id: str


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).casefold()


def _agent_name(agent: dict[str, Any]) -> str:
    full = str(agent.get("name") or "").strip()
    if full:
        return full
    first = str(agent.get("firstName") or "").strip()
    last = str(agent.get("lastName") or "").strip()
    return f"{first} {last}".strip()


def _active_agents(agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for a in agents:
        status = _norm(str(a.get("status") or ""))
        if not status or status in {"active", "enabled"}:
            out.append(a)
    return out


def _pick_single(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    return candidates[0] if len(candidates) == 1 else None


def _first_salesperson(customer: Customer) -> dict[str, Any] | None:
    rows = customer.salespeople or []
    if not rows:
        return None
    first = rows[0]
    return first if isinstance(first, dict) else None


def _salesperson_id_from_stub(stub: dict[str, Any]) -> str:
    return str(stub.get("salesperson_id") or stub.get("id") or "").strip()


def _merge_stub_and_detail(
    stub: dict[str, Any],
    detail: dict[str, Any] | None,
) -> tuple[str, str, str]:
    """
    Build (am_salesperson_id, name, email) for matching.
    Customer embed often omits email; GET /salespeople/{id} supplies it.
    """
    sp_id = _salesperson_id_from_stub(stub)
    if detail:
        sp_id = str(detail.get("id") or sp_id).strip()
        name = str(detail.get("name") or stub.get("name") or "").strip()
        email = str(detail.get("email") or "").strip()
        if not name:
            name = str(stub.get("name") or "").strip()
    else:
        name = str(stub.get("name") or "").strip()
        email = str(stub.get("email") or "").strip()
    return sp_id, name, email


async def resolve_zoho_assignee_for_customer(
    am: AsyncApparelMagicClient,
    zoho: AsyncZohoDeskClient,
    customer: Customer,
) -> ZohoAssigneeMatch | None:
    """
    Match customer.salespeople[0] to a Zoho Desk agent.
    Loads full salesperson from AM via GET /salespeople/{salesperson_id} (email, etc.).
    Priority:
    1) salesperson email exact (if present),
    2) salesperson full name exact,
    3) salesperson first-name exact only when unique.
    """
    stub = _first_salesperson(customer)
    if not stub:
        return None

    lookup_id = _salesperson_id_from_stub(stub)
    detail: dict[str, Any] | None = None
    if lookup_id:
        try:
            rows = await am.get_salesperson_by_id(lookup_id)
            if rows:
                detail = rows[0]
        except Exception:
            logger.exception("Failed to fetch AM salesperson id=%s", lookup_id)

    sp_id, sp_name, sp_email = _merge_stub_and_detail(stub, detail)
    if not sp_name and not sp_email:
        return None

    agents = _active_agents(await zoho.list_agents(limit=100))
    if not agents:
        return None

    if sp_email:
        target_email = _norm(sp_email)
        by_email = [
            a for a in agents if _norm(str(a.get("emailId") or a.get("email") or "")) == target_email
        ]
        chosen = _pick_single(by_email)
        if chosen:
            return ZohoAssigneeMatch(
                assignee_id=str(chosen.get("id") or ""),
                name=_agent_name(chosen),
                email=str(chosen.get("emailId") or chosen.get("email") or ""),
                reason="salesperson_email_exact",
                am_salesperson_name=sp_name,
                am_salesperson_id=sp_id,
            )

    target_name = _norm(sp_name)
    by_full_name = [a for a in agents if _norm(_agent_name(a)) == target_name]
    chosen = _pick_single(by_full_name)
    if chosen:
        return ZohoAssigneeMatch(
            assignee_id=str(chosen.get("id") or ""),
            name=_agent_name(chosen),
            email=str(chosen.get("emailId") or chosen.get("email") or ""),
            reason="salesperson_name_exact",
            am_salesperson_name=sp_name,
            am_salesperson_id=sp_id,
        )

    first_token = _norm(sp_name.split()[0] if sp_name else "")
    if first_token:
        by_first = [
            a for a in agents if _norm(_agent_name(a).split()[0] if _agent_name(a) else "") == first_token
        ]
        chosen = _pick_single(by_first)
        if chosen:
            return ZohoAssigneeMatch(
                assignee_id=str(chosen.get("id") or ""),
                name=_agent_name(chosen),
                email=str(chosen.get("emailId") or chosen.get("email") or ""),
                reason="salesperson_first_name_unique",
                am_salesperson_name=sp_name,
                am_salesperson_id=sp_id,
            )

    logger.info(
        "Could not uniquely match Zoho assignee for AM salesperson name=%r id=%r",
        sp_name,
        sp_id,
    )
    return None
