import asyncio
from typing import Any

import httpx

_DEFAULT_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


async def async_request_with_retries(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_retries: int = 4,
    backoff_base: float = 0.5,
    backoff_max: float = 30.0,
    retry_statuses: frozenset[int] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """
    Async HTTP with retries on transport errors and selected status codes.
    Non-2xx that are not retryable calls raise_for_status().
    """
    retry_on = retry_statuses if retry_statuses is not None else _DEFAULT_RETRY_STATUSES

    for attempt in range(max_retries + 1):
        try:
            resp = await client.request(method, url, **kwargs)
        except httpx.RequestError:
            if attempt >= max_retries:
                raise
            delay = min(backoff_max, backoff_base * (2**attempt))
            await asyncio.sleep(delay)
            continue

        if 200 <= resp.status_code < 300:
            return resp

        if resp.status_code in retry_on and attempt < max_retries:
            delay = min(backoff_max, backoff_base * (2**attempt))
            ra = resp.headers.get("Retry-After")
            if ra is not None:
                try:
                    delay = min(backoff_max, float(ra))
                except ValueError:
                    pass
            await asyncio.sleep(delay)
            continue

        resp.raise_for_status()

    raise RuntimeError("async_request_with_retries: unreachable")
