#!/usr/bin/env python3
"""
Fetch one order from Apparel Magic JSON API and print the full response plus a
line-item summary (product/description, qty, size, color, etc.).

Usage (from repo root, with .env containing APPAREL_MAGIC_API_KEY):

  python scripts/examine_am_order.py
  python scripts/examine_am_order.py 21757
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

# Keys to show per line item if present (API may use others; full JSON still printed)
_LINE_ITEM_KEYS = (
    "description",
    "style_number",
    "product_id",
    "sku_id",
    "size",
    "attr_2",  # color in your model
    "attr_3",
    "upc",
    "qty",
    "unit_price",
    "amount",
    "row_id",
    "id",
)


def _auth_params(settings) -> dict:
    return {
        "token": settings.apparel_magic_api_key,
        "time": int(datetime.now().timestamp()),
    }


def _print_line_items(order_row: dict) -> None:
    items = order_row.get("order_items")
    if not items:
        print("\n--- Line items ---\n  (no `order_items` in response — check raw JSON for other keys)\n")
        return
    if not isinstance(items, list):
        print(f"\n--- Line items ---\n  (unexpected type: {type(items)!r})\n")
        return

    print(f"\n--- Line items ({len(items)}) ---")
    for i, line in enumerate(items, start=1):
        if not isinstance(line, dict):
            print(f"  [{i}] (non-dict: {line!r})")
            continue
        print(f"\n  [{i}]")
        for key in _LINE_ITEM_KEYS:
            if key in line and line[key] not in (None, "", "0.00"):
                print(f"      {key}: {line[key]!r}")
        # Any extra keys not in our list (often product name lives under another name)
        extra = set(line.keys()) - set(_LINE_ITEM_KEYS)
        for key in sorted(extra):
            val = line[key]
            if val not in (None, "", [], {}):
                print(f"      {key}: {val!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Apparel Magic order JSON + line items")
    parser.add_argument("order_id", nargs="?", default="21757", help="Order id in AM")
    args = parser.parse_args()

    settings = get_settings()
    params = _auth_params(settings)

    order_url = f"{BASE_URL}/orders/{args.order_id}"
    r = request_with_retries("GET", order_url, params=dict(params))
    print(f"GET {order_url}\nHTTP {r.status_code}\n")
    if not r.ok:
        print(r.text)
        return 1

    data = r.json()
    print("=== Full API response (JSON) ===")
    print(json.dumps(data, indent=2, default=str))

    response = data.get("response")
    rows = response if isinstance(response, list) else ([response] if response else [])
    if not rows or not isinstance(rows[0], dict):
        return 0

    row = rows[0]
    print("\n=== Order header (selected fields) ===")
    for key in (
        "order_id",
        "customer_id",
        "customer_name",
        "customer_po",
        "date",
        "fulfillment_status",
        "wms_status",
        "is_open",
        "qty",
        "qty_open",
        "qty_shipped",
        "ship_via",
        "address_1",
        "city",
        "state",
        "postal_code",
        "country",
    ):
        if key in row:
            print(f"  {key}: {row[key]!r}")

    _print_line_items(row)

    cid = row.get("customer_id")
    if cid is None:
        return 0

    cust_url = f"{BASE_URL}/customers/{cid}"
    cr = request_with_retries("GET", cust_url, params=dict(params))
    print(f"\n\nGET {cust_url}\nHTTP {cr.status_code}")
    if cr.ok:
        print("\n=== Customer (full JSON) ===")
        print(json.dumps(cr.json(), indent=2, default=str))
    else:
        print(cr.text[:800])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
