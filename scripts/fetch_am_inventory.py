#!/usr/bin/env python3
"""
Fetch Apparel Magic inventory (sync). See .cursor/skills/apparel-magic-inventory-api/.

Examples:

  python scripts/fetch_am_inventory.py product-id 6962
  python scripts/fetch_am_inventory.py sku-id 8248
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


def cmd_sku(sku_id: str) -> int:
    settings = get_settings()
    params = dict(_auth_params(settings))
    url = f"{BASE_URL}/inventory/{sku_id}"
    r = request_with_retries("GET", url, params=params)
    print(f"GET {url}\nHTTP {r.status_code}\n")
    print(json.dumps(r.json(), indent=2, default=str))
    return 0 if r.ok else 1


def cmd_product_id(product_id: str) -> int:
    settings = get_settings()
    params = dict(_auth_params(settings))
    params.update(
        {
            "parameters[0][field]": "product_id",
            "parameters[0][operator]": "=",
            "parameters[0][value]": product_id,
        }
    )
    url = f"{BASE_URL}/inventory"
    r = request_with_retries("GET", url, params=params)
    print(f"GET {url}\nHTTP {r.status_code}\n")
    print(json.dumps(r.json(), indent=2, default=str))
    return 0 if r.ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch AM inventory by sku_id or product_id")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sku = sub.add_parser("sku-id", help="GET /inventory/{sku_id}")
    p_sku.add_argument("sku_id")

    p_prod = sub.add_parser("product-id", help="GET /inventory filtered by product_id =")
    p_prod.add_argument("product_id")

    args = parser.parse_args()
    get_settings()
    if args.command == "sku-id":
        return cmd_sku(args.sku_id)
    if args.command == "product-id":
        return cmd_product_id(args.product_id)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
