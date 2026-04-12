#!/usr/bin/env python3
"""
Exercise the product-inquiry agent (internal search + Apparel Magic) locally.

Requires .env: OPENROUTER_API_KEY, APPAREL_MAGIC_API_KEY, II_HOSTNAME, II_PRODUCT_SEARCH_API_KEY.

Examples:

  python scripts/test_product_inquiry.py --description "navy hoodie"
  python scripts/test_product_inquiry.py --product-id 6962
  python scripts/test_product_inquiry.py --style-number ACCT-CARSNCIR-FCR400
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from app.logger import setup_logging
from app.services.product_inquiry_runner import run_product_inquiry
from app.settings import get_settings


def _build_body(args: argparse.Namespace) -> str:
    if args.description:
        return args.description.strip()
    if args.product_id:
        return (
            f"I am asking about product_id {args.product_id.strip()}.\n\n"
            f"{args.question.strip()}"
        )
    if args.style_number:
        return (
            f"My style number is {args.style_number.strip()}.\n\n"
            f"{args.question.strip()}"
        )
    raise SystemExit("Internal error: no input mode")


async def _run(args: argparse.Namespace) -> int:
    setup_logging()
    get_settings()
    subject = (args.subject or "Product question").strip()
    body = _build_body(args)
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as http:
        settings = get_settings()
        html = await run_product_inquiry(
            ticket_id="test-cli",
            subject=subject,
            body=body,
            http=http,
            settings=settings,
        )
    if html:
        print("Agent chose to post a public reply. HTML:\n")
        print(html)
        return 0
    print("No public reply (silent: no confident match, insufficient data, or error).")
    return 2


def main() -> int:
    p = argparse.ArgumentParser(description="Test product-inquiry agent")
    p.add_argument("--subject", default=None, help="Simulated ticket subject")
    p.add_argument(
        "--question",
        default="What can you tell me about this product based on our catalog?",
        help="Simulated customer question (used with --product-id / --style-number)",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--description", help="Free-text product description (fuzzy search path)")
    g.add_argument("--product-id", help="Apparel Magic product_id (direct fetch path)")
    g.add_argument("--style-number", help="Exact AM style_number (filter path)")
    return asyncio.run(_run(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
