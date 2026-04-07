import time
from typing import Any

import requests

_DEFAULT_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


def request_with_retries(
        method: str,
        url: str,
        *,
        max_retries: int = 4,
        backoff_base: float = 0.5,
        backoff_max: float = 30.0,
        retry_statuses: frozenset[int] | None = None,
        **kwargs: Any,
) -> requests.Response:
    """
    HTTP request with retries on connection/timeout errors and selected status codes.
    Backoff: min(backoff_max, backoff_base * 2**attempt). Uses Retry-After when present.
    Non-2xx after retries or non-retryable status -> resp.raise_for_status().
    """
    retry_on = retry_statuses if retry_statuses is not None else _DEFAULT_RETRY_STATUSES

    for attempt in range(max_retries + 1):
        try:
            resp = requests.request(method, url, timeout=30, **kwargs)
        except requests.RequestException:
            if attempt >= max_retries:
                raise
            delay = min(backoff_max, backoff_base * (2 ** attempt))
            time.sleep(delay)
            continue

        if 200 <= resp.status_code < 300:
            return resp

        if resp.status_code in retry_on and attempt < max_retries:
            delay = min(backoff_max, backoff_base * (2 ** attempt))
            ra = resp.headers.get("Retry-After")
            if ra is not None:
                try:
                    delay = min(backoff_max, float(ra))
                except ValueError:
                    pass
            time.sleep(delay)
            continue

        resp.raise_for_status()

    raise RuntimeError("request_with_retries: unreachable")
