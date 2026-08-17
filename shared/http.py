"""HTTP with retries, for the APIs the generators depend on.

Lifted from finance-newsletter's _notion_request, which was written after a
transient TCP reset aborted a run *after* the Calendar event had been created,
leaving the issue missing from Notion. The other three generators never had
this; routing them through here gives them the same protection.
"""

from __future__ import annotations

import time

import requests

MAX_ATTEMPTS = 5
BACKOFF_BASE = 2.0
MAX_BACKOFF = 30.0

# Transport-level failures that are safe to retry.
RETRYABLE_EXC = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)


def request_with_retry(
    method: str,
    url: str,
    *,
    label: str = "API",
    **kwargs,
) -> requests.Response:
    """Call an HTTP API, retrying transient failures with backoff.

    Retries on connection resets/timeouts, HTTP 429 (honouring Retry-After),
    and 5xx responses. The final response is returned unchanged so callers keep
    using ``raise_for_status()`` for genuine, non-retryable errors.
    """
    kwargs.setdefault("timeout", 30)
    last_exc: Exception | None = None
    resp: requests.Response | None = None

    for attempt in range(MAX_ATTEMPTS):
        is_last = attempt == MAX_ATTEMPTS - 1

        try:
            resp = requests.request(method, url, **kwargs)
            last_exc = None
        except RETRYABLE_EXC as e:
            last_exc, resp = e, None
            if is_last:
                break
            delay = min(BACKOFF_BASE**attempt, MAX_BACKOFF)
            print(
                f"  ⚠ {label} {method} network error "
                f"({e.__class__.__name__}); retry {attempt + 1}/"
                f"{MAX_ATTEMPTS - 1} in {delay:.0f}s"
            )
            time.sleep(delay)
            continue

        if resp.status_code == 429 or resp.status_code >= 500:
            if is_last:
                break
            retry_after = resp.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else 0.0
            except (TypeError, ValueError):
                delay = 0.0
            if delay <= 0:
                delay = min(BACKOFF_BASE**attempt, MAX_BACKOFF)
            print(
                f"  ⚠ {label} {method} returned {resp.status_code}; retry "
                f"{attempt + 1}/{MAX_ATTEMPTS - 1} in {delay:.0f}s"
            )
            time.sleep(delay)
            continue

        return resp

    if last_exc is not None:
        raise last_exc
    return resp
