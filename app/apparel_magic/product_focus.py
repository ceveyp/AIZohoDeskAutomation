"""Subset of Apparel Magic product JSON for LLM grounding (see product inquiry agent)."""

from __future__ import annotations

from typing import Any

# Keys surfaced as ``product_focus`` alongside full ``product`` in tool payloads.
PRODUCT_FOCUS_KEYS: tuple[str, ...] = (
    "description",
    "web_title",
    "web_description",
    "content",
    "price_groups",
    "price_tier",
    "is_returnable",
    "b2b_web_title",
    "b2b_web_description",
    "weight",
    "notes",
    "production_notes",
    "care_instructions",
)


def extract_product_focus(product: dict[str, Any]) -> dict[str, Any]:
    """Return a dict with the focus keys; values may be null if absent on the record."""
    return {k: product.get(k) for k in PRODUCT_FOCUS_KEYS}
