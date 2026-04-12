#!/usr/bin/env python3
"""
Fetch Apparel Magic products (sync HTTP, same auth as the app).

Uses APPAREL_MAGIC_API_KEY from .env. No async client required.

Examples:

  python scripts/fetch_am_products.py id 6962
  python scripts/fetch_am_products.py style ACCT-CARSNCIR-FCR400
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.http_requests import request_with_retries
from app.settings import get_settings

BASE_URL = "https://gamedaysocial.app.apparelmagic.com/api/json"


def _auth_params(settings) -> dict:
    return {
        "token": settings.apparel_magic_api_key,
        "time": int(datetime.now().timestamp()),
    }


def cmd_id(product_id: str) -> int:
    settings = get_settings()
    params = dict(_auth_params(settings))
    url = f"{BASE_URL}/products/{product_id}"
    r = request_with_retries("GET", url, params=params)
    print(f"GET {url}\nHTTP {r.status_code}\n")
    print(json.dumps(r.json(), indent=2, default=str))
    return 0 if r.ok else 1


def cmd_style(style_number: str) -> int:
    settings = get_settings()
    params = dict(_auth_params(settings))
    params.update(
        {
            "parameters[0][field]": "style_number",
            "parameters[0][operator]": "=",
            "parameters[0][value]": style_number,
        }
    )
    url = f"{BASE_URL}/products"
    r = request_with_retries("GET", url, params=params)
    print(f"GET {url}\nHTTP {r.status_code}\n")
    print(json.dumps(r.json(), indent=2, default=str))
    return 0 if r.ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch AM products by id or exact style_number",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_id = sub.add_parser("id", help="GET /products/{product_id}")
    p_id.add_argument("product_id", help="e.g. 6962")

    p_style = sub.add_parser("style", help="GET /products filtered by style_number =")
    p_style.add_argument("style_number", help="e.g. ACCT-CARSNCIR-FCR400")

    args = parser.parse_args()
    get_settings()
    if args.command == "id":
        return cmd_id(args.product_id)
    if args.command == "style":
        return cmd_style(args.style_number)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
