from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.apparel_magic.models import Customer, Order
from app.http.async_http import async_request_with_retries
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
