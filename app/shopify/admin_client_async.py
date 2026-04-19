from __future__ import annotations

from typing import Any

import httpx

from app.async_http import async_request_with_retries
from app.settings import Settings


def _normalize_shop(shop: str) -> str:
    s = shop.strip().lower()
    if not s.endswith(".myshopify.com"):
        s = f"{s}.myshopify.com"
    return s


class AsyncShopifyAdminClient:
    """Minimal Admin REST client for customer search and orders-by-customer."""

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings
        token = (settings.shopify_access_token or "").strip()
        shop = (settings.shopify_shop or "").strip()
        self._token = token
        self._shop = _normalize_shop(shop) if shop else ""
        self._version = (settings.shopify_api_version or "2025-04").strip() or "2025-04"

    def configured(self) -> bool:
        return bool(self._token and self._shop)

    def _headers(self) -> dict[str, str]:
        return {"X-Shopify-Access-Token": self._token}

    async def search_customers_by_email(self, email: str) -> list[dict[str, Any]]:
        """GET customers/search.json?query=email:..."""
        if not self.configured():
            return []
        url = f"https://{self._shop}/admin/api/{self._version}/customers/search.json"
        params = {"query": f"email:{email.strip()}"}
        resp = await async_request_with_retries(
            self._http, "GET", url, headers=self._headers(), params=params
        )
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("customers") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return []
        return [r for r in rows if isinstance(r, dict)]

    async def list_orders_for_customer(
        self,
        customer_id: str | int,
        *,
        limit: int = 50,
        status: str = "any",
    ) -> list[dict[str, Any]]:
        """GET customers/{id}/orders.json (first page)."""
        if not self.configured():
            return []
        cid = str(customer_id).strip()
        url = f"https://{self._shop}/admin/api/{self._version}/customers/{cid}/orders.json"
        lim = max(1, min(int(limit), 250))
        params: dict[str, str | int] = {"limit": lim}
        if status:
            params["status"] = status
        resp = await async_request_with_retries(
            self._http, "GET", url, headers=self._headers(), params=params
        )
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("orders") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return []
        return [r for r in rows if isinstance(r, dict)]
