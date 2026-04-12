#!/usr/bin/env python3
"""
Apparel Magic product search / fetch (JSON API).

Official filtering (see AM KB "API - Filtering Results"):
  - operator must be one of: =, !=, >, <, <=, >=
  - There is NO LIKE / contains / partial text match in the documented API.
  - For "search by name" you need an exact match on a field, or use GET .../products/{id},
    or another AM workflow (e.g. extract style/SKU from the ticket and filter with "=").

  Optional include_type on a parameter: "OR" or "AND" (e.g. two sku_id rows with OR).

Examples (.env with APPAREL_MAGIC_API_KEY):

  python scripts/search_am_products.py id 6962

  python scripts/search_am_products.py search --field style_number --operator = --value ACCT-CARSNCIR-FCR400

  python scripts/search_am_products.py search --field sku_id --operator = --value 25107

  # Two sku_id values combined with OR (second row uses include_type)
  python scripts/search_am_products.py search --field sku_id --operator = --value 1054 \\
      --field2 sku_id --operator2 = --value2 1055 --include-type-1 OR
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

# Per ApparelMagic KB "API - Filtering Results"
DOCUMENTED_OPERATORS = frozenset({"=", "!=", ">", "<", "<=", ">="})


def _auth_params(settings) -> dict:
    return {
        "token": settings.apparel_magic_api_key,
        "time": int(datetime.now().timestamp()),
    }


def _build_products_params(
    settings,
    filters: list[tuple[str, str, str]],
    include_types: list[str | None],
    limit: int | None,
) -> dict:
    params = dict(_auth_params(settings))
    for i, (field, operator, value) in enumerate(filters):
        if operator not in DOCUMENTED_OPERATORS:
            raise SystemExit(
                f"Invalid operator {operator!r}. AM docs allow only: "
                f"{', '.join(sorted(DOCUMENTED_OPERATORS))}"
            )
        params[f"parameters[{i}][field]"] = field
        params[f"parameters[{i}][operator]"] = operator
        params[f"parameters[{i}][value]"] = value
        if i < len(include_types) and include_types[i]:
            params[f"parameters[{i}][include_type]"] = include_types[i]
    if limit is not None:
        params["limit"] = limit
    return params


def _products_get(settings, params: dict):
    url = f"{BASE_URL}/products"
    return request_with_retries("GET", url, params=params), url


def cmd_id(product_id: str) -> int:
    settings = get_settings()
    params = dict(_auth_params(settings))
    url = f"{BASE_URL}/products/{product_id}"
    r = request_with_retries("GET", url, params=params)
    print(f"GET {url}\nHTTP {r.status_code}\n")
    print(json.dumps(r.json(), indent=2, default=str))
    return 0 if r.ok else 1


def cmd_search(
    field: str,
    operator: str,
    value: str,
    field2: str | None,
    operator2: str | None,
    value2: str | None,
    include_type_1: str | None,
    limit: int | None,
) -> int:
    settings = get_settings()
    filters: list[tuple[str, str, str]] = [(field, operator, value)]
    include_types: list[str | None] = [None]
    if field2 or operator2 or value2:
        if not (field2 and operator2 and value2):
            raise SystemExit("Use all of --field2, --operator2, --value2 for a second filter.")
        filters.append((field2, operator2, value2))
        include_types.append(include_type_1)
    params = _build_products_params(settings, filters, include_types, limit)
    r, url = _products_get(settings, params)
    print(f"GET {url}")
    print(f"  {params}")
    print(f"HTTP {r.status_code}\n")
    print(json.dumps(r.json(), indent=2, default=str))
    return 0 if r.ok else 1


def cmd_operators() -> int:
    print(
        "ApparelMagic documented operators (GET filters):\n"
        "  =, !=, >, <, <=, >=\n\n"
        "There is no LIKE/contains in the public filtering docs; use exact match (=)\n"
        "on sku_id, style_number, product_id, upc, etc., or fetch by id.\n"
    )
    return 0


def main() -> int:
    get_settings()

    parser = argparse.ArgumentParser(
        description="Search or fetch Apparel Magic products (per AM filtering docs)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("operators", help="Print allowed operators from AM docs")

    p_id = sub.add_parser("id", help="GET /products/{id}")
    p_id.add_argument("product_id", help="e.g. 6962")

    p_search = sub.add_parser("search", help="GET /products with 1–2 filters")
    p_search.add_argument("--field", required=True)
    p_search.add_argument(
        "--operator",
        default="=",
        choices=sorted(DOCUMENTED_OPERATORS),
        help="AM filter operator (default =)",
    )
    p_search.add_argument("--value", required=True)
    p_search.add_argument("--field2", default=None)
    p_search.add_argument(
        "--operator2",
        default="=",
        choices=sorted(DOCUMENTED_OPERATORS),
    )
    p_search.add_argument("--value2", default=None)
    p_search.add_argument(
        "--include-type-1",
        default=None,
        choices=("OR", "AND"),
        help="include_type for parameters[1] when using second filter",
    )
    p_search.add_argument("--limit", type=int, default=None)

    args = parser.parse_args()
    if args.command == "operators":
        return cmd_operators()
    if args.command == "id":
        return cmd_id(args.product_id)
    if args.command == "search":
        if args.include_type_1 and not args.field2:
            raise SystemExit("--include-type-1 requires --field2, --operator2, and --value2")
        return cmd_search(
            args.field,
            args.operator,
            args.value,
            args.field2,
            args.operator2,
            args.value2,
            args.include_type_1,
            args.limit,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
