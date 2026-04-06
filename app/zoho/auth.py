"""
Interactive Zoho OAuth 2.0 (authorization code) helper.

Set in .env (see .env.example):
  ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REDIRECT_URI
Optional:
  ZOHO_ACCOUNTS_DOMAIN (default accounts.zoho.com — use accounts.zoho.eu, .in, etc. if needed)
  ZOHO_OAUTH_SCOPE (space-separated Desk scopes)

Run: python scratch.py
"""

from __future__ import annotations

import json
import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Event, Thread
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel

from app.settings import get_settings

settings = get_settings()


class ZohoOAuthSettings(BaseModel):
    zoho_client_id: str = settings.zoho_client_id
    zoho_client_secret: str = settings.zoho_client_secret
    zoho_redirect_uri: str = settings.zoho_redirect_uri
    zoho_accounts_domain: str = "accounts.zoho.com"
    zoho_oauth_scope: str = "Desk.tickets.ALL,Desk.basic.READ"


class ZohoOAuthAuthenticator:
    def __init__(self, config: ZohoOAuthSettings) -> None:
        self._cfg = config
        self._token_base = f"https://{config.zoho_accounts_domain.rstrip('/')}/oauth/v2/token"
        self._auth_base = f"https://{config.zoho_accounts_domain.rstrip('/')}/oauth/v2/auth"

    def authorization_url(self, state: str) -> str:
        q = urlencode(
            {
                "scope": self._cfg.zoho_oauth_scope,
                "client_id": self._cfg.zoho_client_id,
                "response_type": "code",
                "redirect_uri": self._cfg.zoho_redirect_uri,
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
            }
        )
        return f"{self._auth_base}?{q}"

    def exchange_code(self, code: str) -> dict:
        body = urlencode(
            {
                "grant_type": "authorization_code",
                "client_id": self._cfg.zoho_client_id,
                "client_secret": self._cfg.zoho_client_secret,
                "redirect_uri": self._cfg.zoho_redirect_uri,
                "code": code,
            }
        ).encode("utf-8")
        req = Request(
            self._token_base,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Token request failed ({e.code}): {detail}") from e
        except URLError as e:
            raise RuntimeError(f"Token request failed: {e}") from e

    def refresh_access_token(self, refresh_token: str) -> dict:
        body = urlencode(
            {
                "grant_type": "refresh_token",
                "client_id": self._cfg.zoho_client_id,
                "client_secret": self._cfg.zoho_client_secret,
                "refresh_token": refresh_token,
            }
        ).encode("utf-8")
        req = Request(
            self._token_base,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Refresh failed ({e.code}): {detail}") from e
        except URLError as e:
            raise RuntimeError(f"Refresh failed: {e}") from e

    def run_browser_flow(self) -> dict:
        state = secrets.token_urlsafe(32)
        redirect = urlparse(self._cfg.zoho_redirect_uri)
        if not redirect.port and redirect.scheme == "http":
            port = 80
        elif not redirect.port and redirect.scheme == "https":
            port = 443
        else:
            port = redirect.port or (443 if redirect.scheme == "https" else 80)

        host = redirect.hostname or "127.0.0.1"
        path_prefix = redirect.path.rstrip("/") or ""

        result: dict[str, str | None] = {"code": None, "error": None, "state": None}
        done = Event()

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == "/favicon.ico":
                    self.send_response(204)
                    self.end_headers()
                    return
                if path_prefix and not parsed.path.startswith(path_prefix):
                    self.send_error(404, "Unknown path")
                    return
                qs = parse_qs(parsed.query)
                result["state"] = (qs.get("state") or [None])[0]
                if qs.get("error"):
                    result["error"] = (qs.get("error") or [""])[0]
                    desc = (qs.get("error_description") or [""])[0]
                    if desc:
                        result["error"] = f"{result['error']}: {desc}"
                else:
                    result["code"] = (qs.get("code") or [None])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                if result["error"]:
                    msg = f"<p>Authorization failed: {result['error']}</p>"
                else:
                    msg = "<p>Authorization complete. You can close this tab.</p>"
                self.wfile.write(
                    f"<!DOCTYPE html><html><body>{msg}</body></html>".encode("utf-8")
                )
                done.set()

            def log_message(self, fmt: str, *args) -> None:
                return

        server = HTTPServer((host, port), CallbackHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()

        auth_url = self.authorization_url(state)
        print("Opening browser. If it does not open, visit this URL:\n", auth_url, sep="")
        webbrowser.open(auth_url)

        if not done.wait(timeout=600):
            server.shutdown()
            thread.join(timeout=5)
            raise TimeoutError("No OAuth callback within 10 minutes.")

        server.shutdown()
        thread.join(timeout=5)

        if result["error"]:
            raise RuntimeError(result["error"])
        if result["state"] != state:
            raise RuntimeError("OAuth state mismatch — aborting.")
        code = result["code"]
        if not code:
            raise RuntimeError("No authorization code received.")
        return self.exchange_code(code)


def main() -> int:
    try:
        cfg = ZohoOAuthSettings()
    except Exception as e:
        print(
            "Missing or invalid OAuth config. Set ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, "
            "and ZOHO_REDIRECT_URI in .env (must match your Zoho API Console app).\n",
            e,
            file=sys.stderr,
        )
        return 1

    auth = ZohoOAuthAuthenticator(cfg)
    try:
        tokens = auth.run_browser_flow()
    except Exception as e:
        print(e, file=sys.stderr)
        return 1

    redacted = {k: v for k, v in tokens.items() if k not in ("access_token", "refresh_token")}
    print("\nToken response (sensitive values omitted from summary):")
    print(json.dumps(redacted, indent=2))
    print("\nFull token JSON (do not commit or share):")
    print(json.dumps(tokens, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
