from __future__ import annotations

import asyncio
from typing import Any

import httpx
import trafilatura

from app.async_http import async_request_with_retries
from app.settings import Settings
from app.zoho.desk.models import Conversation, Thread, Ticket


class AsyncZohoDeskClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._config = settings
        self._access_token: str | None = None
        self._desk_base = "https://desk.zoho.com/api/v1"

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Zoho-oauthtoken {self._access_token}",
            "orgId": self._config.zoho_org_id,
        }

    async def _refresh_access_token(self) -> None:
        data: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": self._config.zoho_refresh_token,
            "client_id": self._config.zoho_client_id,
            "client_secret": self._config.zoho_client_secret,
        }
        url = f"https://{self._config.zoho_accounts_domain.rstrip('/')}/oauth/v2/token"
        resp = await async_request_with_retries(self._http, "POST", url, data=data)
        self._access_token = resp.json()["access_token"]

    async def _api_call(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._access_token:
            await self._refresh_access_token()

        for attempt in range(2):
            headers = {**self._auth_headers()}
            if json_body is not None:
                headers["Content-Type"] = "application/json"
            try:
                resp = await async_request_with_retries(
                    self._http,
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_body,
                )
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401 and attempt == 0:
                    await self._refresh_access_token()
                    continue
                raise

        raise RuntimeError("Zoho API call failed after retry")

    async def get_ticket(self, ticket_id: str) -> Ticket:
        url = f"{self._desk_base}/tickets/{ticket_id}"
        data = await self._api_call("GET", url)
        return Ticket(**data)

    async def list_conversations(self, ticket_id: str) -> list[Conversation]:
        url = f"{self._desk_base}/tickets/{ticket_id}/conversations"
        resp = await self._api_call("GET", url)
        return [Conversation(**c) for c in resp["data"]]

    async def get_thread(self, ticket_id: str, thread_id: str) -> Thread:
        url = f"{self._desk_base}/tickets/{ticket_id}/threads/{thread_id}"
        data = await self._api_call("GET", url)
        thread = Thread(**data)
        if thread.content:
            extracted = await asyncio.to_thread(trafilatura.extract, thread.content)
            if extracted:
                thread.content = extracted
        return thread

    async def add_public_comment(self, ticket_id: str, content: str) -> dict[str, Any]:
        """Post a customer-visible reply. ``content`` should be HTML (e.g. ``<p>``, ``<br />``)."""
        url = f"{self._desk_base}/tickets/{ticket_id}/comments"
        return await self._api_call(
            "POST",
            url,
            json_body={"content": content, "isPublic": True},
        )

    async def update_ticket_status(self, ticket_id: str, status: str) -> dict[str, Any]:
        url = f"{self._desk_base}/tickets/{ticket_id}"
        return await self._api_call("PATCH", url, json_body={"status": status})
