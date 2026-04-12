from __future__ import annotations

import logging
from typing import Any

import httpx

from app.async_http import async_request_with_retries
from app.settings import Settings

logger = logging.getLogger(__name__)


def _search_url(settings: Settings) -> str:
    h = settings.ii_hostname.strip()
    if not h.startswith("http"):
        h = f"https://{h}"
    return f"{h.rstrip('/')}/api/products/search"


def _score_key_and_polarity(row: dict[str, Any]) -> tuple[str | None, bool]:
    """Return (field_name, higher_is_better) if a numeric score-like field exists."""
    for key in ("similarity", "score", "confidence"):
        if key in row and isinstance(row[key], (int, float)):
            return key, True
    for key in ("distance",):
        if key in row and isinstance(row[key], (int, float)):
            return key, False
    return None, True


def apply_search_confidence_filters(
    results: list[dict[str, Any]],
    settings: Settings,
) -> list[dict[str, Any]]:
    """
    Drop weak or ambiguous matches when settings request it.
    Expects higher = better for similarity/score/confidence, lower = better for distance.
    """
    if not results:
        return []
    min_score = settings.product_search_min_confidence
    min_gap = settings.product_search_min_leader_gap
    if min_score is None and min_gap is None:
        return results

    top = results[0]
    key, higher_is_better = _score_key_and_polarity(top)
    if key is None:
        logger.info(
            "product_search_confidence_skipped",
            extra={"reason": "no_score_field_on_hits"},
        )
        return results

    try:
        v0 = float(top[key])
        if min_score is not None:
            if higher_is_better:
                if v0 < min_score:
                    return []
            else:
                if v0 > min_score:
                    return []

        if min_gap is not None and len(results) > 1:
            v1 = float(results[1][key])
            gap = (v0 - v1) if higher_is_better else (v1 - v0)
            if gap < min_gap:
                return []
    except (TypeError, ValueError):
        logger.warning("product_search_confidence_parse_failed", extra={"key": key})
        return results

    return results


class AsyncInternalInventoryClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings

    async def search_products(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        url = _search_url(self._settings)
        headers = {"X-API-Key": self._settings.ii_product_search_api_key}
        params = {"q": query, "limit": limit}
        resp = await async_request_with_retries(
            self._http,
            "GET",
            url,
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            logger.warning(
                "internal_inventory_search_unexpected_shape",
                extra={"type": type(data).__name__},
            )
            return []
        out: list[dict[str, Any]] = [x for x in data if isinstance(x, dict)]
        return apply_search_confidence_filters(out, self._settings)
