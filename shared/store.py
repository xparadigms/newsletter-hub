"""Supabase writes, over PostgREST.

Plain requests rather than the supabase SDK: the SDK pulls httpx, gotrue,
storage3 and realtime into requirements.txt to serve one HTTP call.

The generators write with the secret key, which bypasses RLS. It must never
reach the browser — the website reads with the publishable key under a
select-only policy.
"""

from __future__ import annotations

import os
from typing import Any

from . import http

TABLE = "newsletter"


def _config() -> tuple[str, str]:
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SECRET_KEY") or ""
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY must be set")
    return url, key


def _headers(key: str, prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def upsert_issue(row: dict[str, Any]) -> dict[str, Any]:
    """Insert or replace one issue, returning the stored row.

    Conflicts resolve on run_key, so a same-day rerun replaces its own row
    instead of adding a duplicate. `slug` is deliberately omitted by callers:
    the database trigger derives it and preserves an existing one, so a rerun
    whose headline changed keeps the URL it published under.
    """
    url, key = _config()
    row = {k: v for k, v in row.items() if k != "slug"}
    resp = http.request_with_retry(
        "POST",
        f"{url}/rest/v1/{TABLE}?on_conflict=run_key",
        label="Supabase",
        headers=_headers(key, "resolution=merge-duplicates,return=representation"),
        json=[row],
    )
    resp.raise_for_status()
    stored = resp.json()
    return stored[0] if isinstance(stored, list) and stored else {}


def patch_issue(run_key: str, fields: dict[str, Any]) -> None:
    """Update a stored issue — used to attach the Notion page once mirrored."""
    url, key = _config()
    resp = http.request_with_retry(
        "PATCH",
        f"{url}/rest/v1/{TABLE}?run_key=eq.{run_key}",
        label="Supabase",
        headers=_headers(key, "return=minimal"),
        json=fields,
    )
    resp.raise_for_status()


def ping_revalidate(section: str, slug: str) -> None:
    """Ask the site to drop its cached list and body for one issue.

    Best-effort: the lists expire on their own within five minutes, so a failure
    here delays the new issue appearing but loses nothing.
    """
    site = (os.environ.get("SITE_URL") or "").rstrip("/")
    secret = os.environ.get("REVALIDATE_SECRET")
    if not site or not secret:
        return
    try:
        http.request_with_retry(
            "POST",
            f"{site}/api/revalidate",
            label="revalidate",
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
            json={"section": section, "slug": slug},
        )
    except Exception as e:  # noqa: BLE001 - never fail a run over a cache ping
        print(f"  ⚠ revalidate ping failed: {e}")
