from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.apparel_magic.models import Customer, Order
from app.async_http import async_request_with_retries
from app.logger import get_logger
from app.settings import Settings

logger = get_logger(__name__)


class AsyncApparelMagicClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings
        self._base_url = "https://gamedaysocial.app.apparelmagic.com/api/json"

    def _add_auth_params(self, params: dict[str, Any]) -> None:
        params.update(
            {
                "token": self._settings.apparel_magic_api_key,
                "time": int(datetime.now().timestamp()),
            }
        )

    async def _api_call(
            self,
            method: str,
            url: str,
            *,
            params: dict[str, Any] | None = None,
            data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if params is not None:
            self._add_auth_params(params)
        elif data is not None:
            self._add_auth_params(data)
        else:
            params = {}
            self._add_auth_params(params)
        resp = await async_request_with_retries(
            self._http,
            method,
            url,
            params=params,
            data=data,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_customer_by_email(self, email: str) -> Customer | None:
        url = f"{self._base_url}/customers"
        params = {
            "parameters[0][field]": "email",
            "parameters[0][operator]": "=",
            "parameters[0][value]": email,
        }
        try:
            resp = await self._api_call("GET", url, params=params)
            customers = resp.get("response") or []
            if not customers:
                return None
            return Customer(**customers[0])
        except Exception as e:
            logger.exception("Error fetching customer %s", email)
            raise RuntimeError(f"Error fetching customer ({email}): {e}") from e

    async def get_order_by_id(self, order_id: str) -> Order | None:
        url = f"{self._base_url}/orders/{order_id}"
        try:
            resp = await self._api_call("GET", url)
            orders = resp.get("response") or []
            if not orders:
                return None
            return Order(**orders[0])
        except Exception as e:
            logger.exception("Error fetching order %s", order_id)
            raise RuntimeError(f"Error fetching order ({order_id}): {e}") from e

    async def get_orders_by_customer_id(self, customer_id: str) -> list[Order]:
        url = f"{self._base_url}/orders"
        params = {
            "parameters[0][field]": "customer_id",
            "parameters[0][operator]": "=",
            "parameters[0][value]": customer_id,
        }
        try:
            resp = await self._api_call("GET", url, params=params)
            orders = resp.get("response") or []
            if not orders:
                return []
            return [Order(**o) for o in orders]
        except Exception as e:
            logger.exception("Error fetching orders for customer %s", customer_id)
            raise RuntimeError(f"Error fetching orders for customer ({customer_id}): {e}") from e

    async def get_raw_product_by_id(self, product_id: str) -> dict[str, Any] | None:
        """Single product row from AM ``GET /products/{id}`` (first element of ``response``)."""
        url = f"{self._base_url}/products/{product_id}"
        try:
            resp = await self._api_call("GET", url)
            rows = resp.get("response") or []
            if not rows:
                return None
            row = rows[0]
            return row if isinstance(row, dict) else None
        except Exception as e:
            logger.exception("Error fetching product %s", product_id)
            raise RuntimeError(f"Error fetching product ({product_id}): {e}") from e

    async def get_raw_products_by_style_number(self, style_number: str) -> list[dict[str, Any]]:
        """Products where ``style_number`` equals the given value (exact AM filter)."""
        url = f"{self._base_url}/products"
        params = {
            "parameters[0][field]": "style_number",
            "parameters[0][operator]": "=",
            "parameters[0][value]": style_number,
        }
        try:
            resp = await self._api_call("GET", url, params=params)
            rows = resp.get("response") or []
            return [r for r in rows if isinstance(r, dict)]
        except Exception as e:
            logger.exception("Error fetching products by style_number %s", style_number)
            raise RuntimeError(
                f"Error fetching products by style_number ({style_number}): {e}"
            ) from e

    async def get_raw_inventory_by_product_id(self, product_id: str) -> list[dict[str, Any]]:
        """SKU rows from ``GET /inventory`` filtered by ``product_id`` (exact match)."""
        url = f"{self._base_url}/inventory"
        params = {
            "parameters[0][field]": "product_id",
            "parameters[0][operator]": "=",
            "parameters[0][value]": product_id,
        }
        try:
            resp = await self._api_call("GET", url, params=params)
            rows = resp.get("response") or []
            return [r for r in rows if isinstance(r, dict)]
        except Exception as e:
            logger.exception("Error fetching inventory for product_id %s", product_id)
            raise RuntimeError(
                f"Error fetching inventory for product_id ({product_id}): {e}"
            ) from e

    async def get_invoice_by_id(self, invoice_id: str) -> list[dict[str, Any]]:
        """Get invoice by ID"""
        url = f"{self._base_url}/invoices/{invoice_id}"
        try:
            resp = await self._api_call("GET", url)
            rows = resp.get("response") or []
            return [r for r in rows if isinstance(r, dict)]
        except Exception as e:
            logger.exception("Error fetching invoice for invoice ID %s", invoice_id)
            raise RuntimeError(
                f"Error fetching inventory for product_id ({invoice_id}): {e}"
            ) from e
