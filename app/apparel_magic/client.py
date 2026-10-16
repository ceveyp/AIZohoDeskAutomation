from datetime import datetime
from typing import Dict, List

from app.apparel_magic.models import Customer, Order
from app.http_requests import request_with_retries
from app.logger import get_logger, setup_logging
from app.settings import get_settings

logger = get_logger(__name__)


class ApparelMagicClient:
    def __init__(self):
        self._settings = get_settings()
        self._base_url = "https://retailer.app.apparelmagic.com/api/json"

    def _add_auth_params(self, params: Dict):
        params.update({
            "token": self._settings.apparel_magic_api_key,
            "time": int(datetime.now().timestamp())
        })

    def _api_call(
            self,
            method: str,
            url: str,
            params: Dict | None = None,
            data: Dict | None = None
    ) -> Dict:
        try:
            if params:
                self._add_auth_params(params)
            elif data:
                self._add_auth_params(data)
            else:
                params = {}
                self._add_auth_params(params)
            resp = request_with_retries(method, url, params=params, data=data)
            if not resp.ok:
                raise RuntimeError(f"Apparel Magic API error: {resp.text}")
            return resp.json()
        except Exception as e:
            logger.exception(e)
            raise e

    def get_customer_by_email(self, email: str) -> Customer | None:
        url = f"{self._base_url}/customers"
        params = {
            "parameters[0][field]": "email",
            "parameters[0][operator]": "=",
            "parameters[0][value]": email
        }
        try:
            resp = self._api_call('GET', url, params)
            customers = resp["response"]
            if not customers:
                return
            return Customer(**customers.pop())
        except Exception as e:
            logger.exception(e)
            raise RuntimeError(f"Error fetching customer ({email}): {e}")

    def get_order_by_id(self, order_id: str) -> Order | None:
        url = f"{self._base_url}/orders/{order_id}"
        try:
            resp = self._api_call('GET', url)
            orders = resp["response"]
            if not orders:
                return
            return Order(**orders.pop())
        except Exception as e:
            logger.exception(e)
            raise RuntimeError(f"Error fetching order ({order_id}): {e}")

    def get_orders_by_customer_id(self, customer_id: str) -> List[Order] | None:
        url = f"{self._base_url}/orders"
        params = {
            "parameters[0][field]": "customer_id",
            "parameters[0][operator]": "=",
            "parameters[0][value]": customer_id
        }
        try:
            resp = self._api_call('GET', url, params=params)
            orders = resp["response"]
            if not orders:
                return
            return [Order(**order) for order in orders]
        except Exception as e:
            logger.exception(e)
            raise RuntimeError(f"Error fetching orders for customer ({customer_id}): {e}")


if __name__ == '__main__':
    setup_logging()
    print(ApparelMagicClient().get_orders_by_customer_id("10768"))
