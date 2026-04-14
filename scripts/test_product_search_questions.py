#!/usr/bin/env python3
"""
Catalog of natural-language ticket questions for exercising Product Search filters.

Each entry documents which API-style filters the question is meant to stress
(q, team, category, color, season, in_stock). The product-inquiry agent should
map these to search_catalog(...) with AND semantics where appropriate.

Usage:

  python scripts/test_product_search_questions.py
  python scripts/test_product_search_questions.py --by-filter
  python scripts/test_product_search_questions.py --run
  python scripts/test_product_search_questions.py --run --only q-hoodie-keyword,team-full-name
  python scripts/test_product_search_questions.py --run --group single_filter

--run calls the real product-inquiry agent (OpenRouter, internal search API, Apparel Magic).
Requires .env: OPENROUTER_API_KEY, APPAREL_MAGIC_API_KEY, II_HOSTNAME, II_PRODUCT_SEARCH_API_KEY.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dataclasses import dataclass

import httpx

from app.logger import setup_logging
from app.services.product_inquiry_runner import run_product_inquiry
from app.settings import get_settings


@dataclass
class SearchQuestion:
    """One ticket-style scenario."""

    id: str
    subject: str
    body: str
    filters_exercised: list[str]  # subset of q, team, category, color, season, in_stock
    notes: str = ""

    def as_ticket(self) -> str:
        subj = self.subject.strip()
        bod = self.body.strip()
        if subj:
            return f"Subject: {subj}\n\n{bod}"
        return bod


# --- Single-filter emphasis (each row still valid for "at least one" criterion) ---

SINGLE_FILTER_QUESTIONS: list[SearchQuestion] = [
    SearchQuestion(
        id="q-hoodie-keyword",
        subject="Hoodie search",
        body="Do you have anything with an archival arch hoodie in the description?",
        filters_exercised=["q"],
        notes="Free-text q across description / web_title / web_description.",
    ),
    SearchQuestion(
        id="q-style-phrase",
        subject="Product name",
        body="I'm looking for Circle CMF Crew — do you carry that?",
        filters_exercised=["q"],
    ),
    SearchQuestion(
        id="team-full-name",
        subject="School gear",
        body="What Mississippi State apparel do you sell?",
        filters_exercised=["team"],
        notes="Team as institution name.",
    ),
    SearchQuestion(
        id="team-code",
        subject="MSU items",
        body="Do you have MSST products in your catalog?",
        filters_exercised=["team"],
        notes="Team as code if customer uses abbreviations.",
    ),
    SearchQuestion(
        id="category-only",
        subject="Hoodies",
        body="What hoodies do you have? I don't care which school.",
        filters_exercised=["category"],
        notes="category alone satisfies API minimum.",
    ),
    SearchQuestion(
        id="color-only",
        subject="Burnt orange",
        body="Show me everything you have in burnt orange.",
        filters_exercised=["color"],
    ),
    SearchQuestion(
        id="season-only",
        subject="Fall drop",
        body="What's in the Fall 25 collection?",
        filters_exercised=["season"],
    ),
    SearchQuestion(
        id="season-core",
        subject="Core line",
        body="Do you still have CORE season basics listed?",
        filters_exercised=["season"],
        notes="Season token like CORE / DISCO per API docs.",
    ),
]

# --- in_stock (always combined with at least one text dimension in real API calls) ---

IN_STOCK_QUESTIONS: list[SearchQuestion] = [
    SearchQuestion(
        id="team-in-stock",
        subject="Alabama in stock",
        body="What Alabama items do you actually have in stock right now?",
        filters_exercised=["team", "in_stock"],
    ),
    SearchQuestion(
        id="q-in-stock",
        subject="Navy hoodie availability",
        body="Do you have any navy hoodies available to ship?",
        filters_exercised=["q", "in_stock"],
    ),
    SearchQuestion(
        id="category-team-in-stock",
        subject="Iowa hoodies",
        body="Which Iowa hoodies are in stock?",
        filters_exercised=["team", "category", "in_stock"],
        notes="Matches skill example: team + category + in_stock AND.",
    ),
    SearchQuestion(
        id="explicit-not-in-stock",
        subject="Sold out check",
        body="List Oregon trucker hats that are currently out of stock.",
        filters_exercised=["team", "category", "in_stock"],
        notes="Agent may use in_stock=false if customer asks for unavailable items.",
    ),
]

# --- Multi-filter AND (no in_stock) ---

COMBO_QUESTIONS: list[SearchQuestion] = [
    SearchQuestion(
        id="team-category",
        subject="MSU hoodies",
        body="Do you sell Mississippi State hoodies?",
        filters_exercised=["team", "category"],
    ),
    SearchQuestion(
        id="team-color",
        subject="Black Iowa gear",
        body="What Iowa products do you have in black?",
        filters_exercised=["team", "color"],
    ),
    SearchQuestion(
        id="team-season",
        subject="Spring Texas A&M",
        body="What's new for Texas A&M in Spring 2026?",
        filters_exercised=["team", "season"],
    ),
    SearchQuestion(
        id="category-color",
        subject="White crews",
        body="Do you have white crewneck sweatshirts?",
        filters_exercised=["category", "color"],
    ),
    SearchQuestion(
        id="category-season",
        subject="Fall hats",
        body="What trucker hats are in the Fall 25 line?",
        filters_exercised=["category", "season"],
    ),
    SearchQuestion(
        id="q-team",
        subject="Bama tee",
        body="I'm looking for a soft Alabama t-shirt — anything like that?",
        filters_exercised=["q", "team"],
        notes="May collapse to q or team+q depending on agent.",
    ),
    SearchQuestion(
        id="color-season",
        subject="Fall colors",
        body="What burnt orange pieces are tagged Fall 25?",
        filters_exercised=["color", "season"],
    ),
    SearchQuestion(
        id="four-way",
        subject="Specific browse",
        body="Show me in-stock black Iowa hoodies from Fall 25.",
        filters_exercised=["team", "category", "color", "season", "in_stock"],
    ),
]

# --- limit / breadth (behavioral; limit is tool param not customer language) ---

LIMIT_HINT_QUESTIONS: list[SearchQuestion] = [
    SearchQuestion(
        id="broad-top-n",
        subject="Catalog browse",
        body="Give me an overview of the first several Georgia items you carry — just a sample, not every SKU.",
        filters_exercised=["team"],
        notes="Agent may use a modest limit and summarize; not a separate API filter.",
    ),
]

# --- Edge / ambiguity (still valid tickets) ---

EDGE_QUESTIONS: list[SearchQuestion] = [
    SearchQuestion(
        id="vague-availability",
        subject="In stock?",
        body="Is the Arch Comfort Hoodie in stock?",
        filters_exercised=["q", "in_stock"],
        notes="May need q then AM+inventory for exact SKUs.",
    ),
    SearchQuestion(
        id="style-number-ticket",
        subject="Style code",
        body="Do you have style ACCT-CARSNCIR-FCR400?",
        filters_exercised=[],
        notes="Expect style_number path, not search_catalog — included to contrast filter tests.",
    ),
    SearchQuestion(
        id="product-id-ticket",
        subject="Product 6962",
        body="Tell me about product 6962.",
        filters_exercised=[],
        notes="Expect product_id path — contrast with search filters.",
    ),
]

ALL_GROUPS: list[tuple[str, list[SearchQuestion]]] = [
    ("single_filter", SINGLE_FILTER_QUESTIONS),
    ("in_stock", IN_STOCK_QUESTIONS),
    ("combinations", COMBO_QUESTIONS),
    ("limit_behavior", LIMIT_HINT_QUESTIONS),
    ("edge_and_non_search", EDGE_QUESTIONS),
]


def _flatten() -> list[SearchQuestion]:
    out: list[SearchQuestion] = []
    for _, rows in ALL_GROUPS:
        out.extend(rows)
    return out


def _print_default() -> None:
    for group_name, rows in ALL_GROUPS:
        print(f"## {group_name}\n")
        for q in rows:
            flt = ", ".join(q.filters_exercised) if q.filters_exercised else "(non-search path)"
            print(f"  [{q.id}]  filters: {flt}")
            if q.subject:
                print(f"    subject: {q.subject}")
            print(f"    body: {q.body}")
            if q.notes:
                print(f"    notes: {q.notes}")
            print()
        print()


def _print_by_filter() -> None:
    filters = ["q", "team", "category", "color", "season", "in_stock"]
    by_f: dict[str, list[SearchQuestion]] = {f: [] for f in filters}
    for q in _flatten():
        for f in q.filters_exercised:
            if f in by_f:
                by_f[f].append(q)

    for f in filters:
        print(f"## filter: {f}\n")
        seen: set[str] = set()
        for q in by_f[f]:
            if q.id in seen:
                continue
            seen.add(q.id)
            print(f"  - {q.id}: {q.body[:77]}{'…' if len(q.body) > 77 else ''}")
        print()


def _group_names() -> set[str]:
    return {name for name, _ in ALL_GROUPS}


def _questions_for_run(only: str, groups: list[str]) -> list[SearchQuestion]:
    only_ids = [s.strip() for s in only.split(",") if s.strip()]
    if only_ids:
        by_id = {q.id: q for q in _flatten()}
        missing = set(only_ids) - by_id.keys()
        if missing:
            raise SystemExit(f"Unknown question id(s): {sorted(missing)}")
        return [by_id[i] for i in only_ids]
    group_set = set(groups)
    if group_set:
        known = _group_names()
        bad = group_set - known
        if bad:
            raise SystemExit(f"Unknown group(s): {sorted(bad)}. Valid: {sorted(known)}")
        out: list[SearchQuestion] = []
        for name, rows in ALL_GROUPS:
            if name in group_set:
                out.extend(rows)
        return out
    return _flatten()


async def _run_agent(args: argparse.Namespace) -> int:
    setup_logging()
    settings = get_settings()
    try:
        questions = _questions_for_run(args.only or "", args.group or [])
    except SystemExit as e:
        print(e.args[0], file=sys.stderr)
        return 2

    print(f"Running {len(questions)} scenario(s) through product_inquiry…\n")
    timeout = httpx.Timeout(args.timeout)
    exit_code = 0
    async with httpx.AsyncClient(timeout=timeout) as http:
        for i, q in enumerate(questions, start=1):
            flt = ", ".join(q.filters_exercised) if q.filters_exercised else "(non-search path)"
            sep = "=" * 72
            print(sep)
            print(f"[{i}/{len(questions)}] {q.id}  filters: {flt}")
            print(f"subject: {q.subject}")
            print(f"body: {q.body}")
            if q.notes:
                print(f"notes: {q.notes}")
            print("--- agent response ---")
            html = await run_product_inquiry(
                ticket_id=f"test-search-{q.id}",
                subject=q.subject,
                body=q.body,
                http=http,
                settings=settings,
            )
            if html:
                print(html)
            else:
                print("(No public reply: agent stayed silent, validation failed, or an error occurred.)")
                exit_code = 1
            print()
            if args.delay_s > 0 and i < len(questions):
                await asyncio.sleep(args.delay_s)
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--by-filter",
        action="store_true",
        help="Group question IDs under each filter name (q, team, …).",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run each selected question through run_product_inquiry (live APIs + LLM).",
    )
    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated question ids (with --run). Overrides --group when non-empty.",
    )
    parser.add_argument(
        "--group",
        action="append",
        default=[],
        metavar="NAME",
        help="Repeatable group name: single_filter, in_stock, combinations, limit_behavior, "
        "edge_and_non_search. Used with --run if --only is omitted.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="HTTP client timeout seconds per request (default 120).",
    )
    parser.add_argument(
        "--delay-s",
        type=float,
        default=0.0,
        help="Pause between scenarios to reduce rate limits (default 0).",
    )
    args = parser.parse_args()

    if args.run:
        return asyncio.run(_run_agent(args))
    if args.by_filter:
        _print_by_filter()
    else:
        _print_default()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
