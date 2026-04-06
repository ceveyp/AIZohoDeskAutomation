from typing import Dict, List

import requests
import trafilatura

from app.settings import get_settings
from app.zoho.desk.models import Ticket, Conversation, Thread


class ZohoDeskClient:
    def __init__(self):
        self._config = get_settings()
        self._session = requests.Session()
        self._access_token = None
        self._refresh_token = self._config.zoho_refresh_token
        self._desk_base_url = "https://desk.zoho.com/api/v1"

    def _set_auth_headers(self, access_token: str):
        self._session.headers = {
            "Authorization": f"Zoho-oauthtoken {access_token}",
            "orgId": self._config.zoho_org_id
        }

    def _refresh_access_token(self):
        url = "https://accounts.zoho.com/oauth/v2/token"
        data = {
            "refresh_token": self._config.zoho_refresh_token,
            "client_id": self._config.zoho_client_id,
            "client_secret": self._config.zoho_client_secret,
            "scope": self._config.zoho_scopes,
            "redirect_url": self._config.zoho_redirect_uri,
            "grant_type": "refresh_token"
        }
        resp = self._session.post(url, params=data, timeout=30)
        if not resp.ok:
            raise RuntimeError(f"Could not authenticate with Zoho refresh token: {resp.text}")
        token = resp.json()
        self._access_token = token["access_token"]
        self._set_auth_headers(self._access_token)

    def _api_call(
            self,
            method: str,
            url: str,
            params: Dict | None = None,
            data: Dict | None = None
    ) -> Dict:
        if not self._access_token:
            self._refresh_access_token()
        resp = self._session.request(
            method=method,
            url=url,
            params=params,
            data=data,
            timeout=30
        )
        if not resp.ok:
            if resp.status_code == 401:
                self._refresh_access_token()
            else:
                raise RuntimeError(f"Zoho API error: {resp.text}")
        return resp.json()

    def list_tickets(self, count=10) -> List[Ticket]:
        url = f"{self._desk_base_url}/tickets"
        params = {"limit": count}
        resp = self._api_call('GET', url, params)
        return [Ticket(**ticket) for ticket in resp["data"]]

    def list_conversations(self, ticket_id: str) -> List[Conversation]:
        url = f"{self._desk_base_url}/tickets/{ticket_id}/conversations"
        resp = self._api_call('GET', url)
        return [Conversation(**conversation) for conversation in resp["data"]]

    def get_thread(self, ticket_id: str, thread_id: str) -> Thread:
        url = f"{self._desk_base_url}/tickets/{ticket_id}/threads/{thread_id}"
        thread = Thread(**self._api_call('GET', url))
        thread.content = trafilatura.extract(thread.content)
        return thread
