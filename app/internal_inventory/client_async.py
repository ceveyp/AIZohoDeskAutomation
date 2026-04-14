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


SEARCH_LIMIT_MIN = 1
SEARCH_LIMIT_DEFAULT = 20
SEARCH_LIMIT_MAX = 50


class AsyncInternalInventoryClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings

    async def search_catalog(
        self,
        *,
        q: str = "",
        team: str = "",
        category: str = "",
        color: str = "",
        season: str = "",
        in_stock: bool | None = None,
        limit: int = SEARCH_LIMIT_DEFAULT,
    ) -> list[dict[str, Any]]:
        """
        GET /api/products/search with optional filters. At least one of q, team, category, color, season
        must be non-empty or the server returns 400 — validate before calling.
        """
        q_s = (q or "").strip()
        team_s = (team or "").strip()
        cat_s = (category or "").strip()
        color_s = (color or "").strip()
        season_s = (season or "").strip()
        if not any((q_s, team_s, cat_s, color_s, season_s)):
            raise ValueError(
                "At least one of q, team, category, color, or season must be non-empty."
            )
        lim = max(SEARCH_LIMIT_MIN, min(SEARCH_LIMIT_MAX, int(limit)))
        params: dict[str, str | int] = {"limit": lim}
        if q_s:
            params["q"] = q_s
        if team_s:
            params["team"] = team_s
        if cat_s:
            params["category"] = cat_s
        if color_s:
            params["color"] = color_s
        if season_s:
            params["season"] = season_s
        if in_stock is True:
            params["in_stock"] = "true"
        elif in_stock is False:
            params["in_stock"] = "false"

        log_extra = {
            "has_q": bool(q_s),
            "q_prefix": (q_s[:80] + "…") if len(q_s) > 80 else (q_s or None),
            "team": team_s or None,
            "category": cat_s or None,
            "color": color_s or None,
            "season": season_s or None,
            "in_stock": in_stock,
            "limit": lim,
        }
        logger.info("internal_inventory_search_catalog_request", extra=log_extra)

        url = _search_url(self._settings)
        headers = {"X-API-Key": self._settings.ii_product_search_api_key}
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
        filtered = apply_search_confidence_filters(out, self._settings)
        logger.info(
            "internal_inventory_search_catalog_response",
            extra={**log_extra, "raw_count": len(out), "returned_count": len(filtered)},
        )
        return filtered

    async def search_products(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Backward-compatible text-only search (q + limit)."""
        q = (query or "").strip()
        if not q:
            return []
        lim = max(SEARCH_LIMIT_MIN, min(SEARCH_LIMIT_MAX, int(limit)))
        return await self.search_catalog(q=q, limit=lim)
