#!/usr/bin/env python3
"""
Classify a simulated ticket (same text shape as the webhook), then run the product-inquiry agent if intent matches.

Requires .env (OpenRouter, AM, II search, etc.) when running the product agent.

Examples:

  python scripts/test_ticket_intent_and_agent.py --subject "question" --description "Do you have this in stock Accent On Dance Carson Circle?"
  python scripts/test_ticket_intent_and_agent.py --subject "Shipping" --description "Where is order 12345?"
  python scripts/test_ticket_intent_and_agent.py --subject "Hi" --description "..." --skip-agent
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from app.logger import setup_logging
from app.services.product_inquiry_runner import run_product_inquiry
from app.settings import get_settings
from app.zoho.desk.intent_classifier import IntentClassifier


async def _run(subject: str, description: str, skip_agent: bool) -> int:
    setup_logging()
    get_settings()
    body_for_llm = f"{subject}\n\n{description}".strip()

    classifier = IntentClassifier()
    intent = await classifier.classify_async(subject, body_for_llm or subject)

    print("=== Intent classification ===")
    print(json.dumps(intent.model_dump(mode="json"), indent=2, default=str))
    print()

    if intent.intent != "product_inquiry":
        print("Skipping product-inquiry agent (intent is not product_inquiry).")
        return 0

    if skip_agent:
        print("Skipping product-inquiry agent (--skip-agent).")
        return 0

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as http:
        settings = get_settings()
        html = await run_product_inquiry(
            ticket_id="test-cli",
            subject=subject,
            body=body_for_llm or subject,
            http=http,
            settings=settings,
        )

    print("=== Product-inquiry agent (public comment HTML, if any) ===")
    if html:
        print(html)
        return 0
    print("(No public reply — silent path: no confident match, insufficient data, or error.)")
    return 2


def main() -> int:
    p = argparse.ArgumentParser(
        description="Classify subject+description like the webhook; run product agent when intent is product_inquiry",
    )
    p.add_argument("--subject", default="", help="Ticket subject (empty ok)")
    p.add_argument(
        "--description",
        default="",
        help="Ticket body / description plain text",
    )
    p.add_argument(
        "--skip-agent",
        action="store_true",
        help="Only run intent classification (no OpenRouter product agent)",
    )
    args = p.parse_args()
    if not args.subject.strip() and not args.description.strip():
        p.error("Provide at least one of --subject or --description")
    return asyncio.run(_run(args.subject, args.description, args.skip_agent))


if __name__ == "__main__":
    raise SystemExit(main())
