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


def configured() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SECRET_KEY"))


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
    if not configured():
        # During the migration the secrets may not exist yet. Skipping keeps the
        # Notion and Calendar mirrors working rather than failing the whole run
        # before either has happened — the same posture as a missing
        # NOTION_TOKEN. A configured-but-failing write still raises.
        print("  ⚠ SUPABASE_URL/SUPABASE_SECRET_KEY not set, skipping Supabase.")
        return {}

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


def recent_issues(section: str, limit: int = 3) -> list[dict[str, Any]]:
    """Every row of the last `limit` issues, newest first, with source text.

    Feeds the on-demand editions: an extra issue is only worth reading if it
    covers stories the recent ones did not, and the source text carries both
    the headlines and the 🔗 links that identify them.

    Counted in issues, not rows. Startup, Business and Rails publish one row
    per story now (shared/split.py), so a row limit of 4 would have shrunk the
    lookback from four issues to about one. An issue is an (issue_date,
    edition) pair; every row of it carries the whole issue's source text and
    its own story title.
    """
    try:
        base, key = _config()
        resp = http.request_with_retry(
            "GET",
            f"{base}/rest/v1/{TABLE}"
            f"?section=eq.{section}&select=title,source_text,issue_date,edition"
            f"&order=issue_date.desc,edition.desc&limit={limit * 8}",
            label="Supabase",
            headers=_headers(key),
        )
        resp.raise_for_status()
        rows = resp.json()
        issues: list[tuple[Any, Any]] = []
        for r in rows:
            key_ = (r.get("issue_date"), r.get("edition"))
            if key_ not in issues:
                issues.append(key_)
        keep = set(issues[:limit])
        return [r for r in rows if (r.get("issue_date"), r.get("edition")) in keep]
    except Exception as e:  # noqa: BLE001 — no exclusions is worse, not fatal
        print(f"  ⚠ could not read recent issues (non-fatal): {e}")
        return []


def recent_titles(section: str, limit: int = 10) -> list[str]:
    """Titles of the last `limit` issues, newest first. Empty on any failure.

    Insight sources are podcasts and essays, which publish weekly, so the same
    episode stays inside the lookback window for days. Handing the model what it
    already covered is what stops it writing up the same interview twice — the
    failure that produced four identical startup issues in August.
    """
    try:
        base, key = _config()
        resp = http.request_with_retry(
            "GET",
            f"{base}/rest/v1/{TABLE}"
            f"?section=eq.{section}&select=title&order=issue_date.desc&limit={limit}",
            label="Supabase",
            headers=_headers(key),
        )
        resp.raise_for_status()
        return [r["title"] for r in resp.json() if r.get("title")]
    except Exception as e:  # noqa: BLE001 — a missing exclusion list is not fatal
        print(f"  ⚠ could not read recent titles (non-fatal): {e}")
        return []


def next_issue_number(section: str, issue_date: str, edition: int = 1) -> int:
    """The issue number for a run, read from what is stored rather than the run.

    github.run_number counts dry runs and failed runs too, which leaves gaps a
    reader can see. Rerunning a day that is already stored keeps that day's
    number; anything else takes the next one. 1 when the section is empty or
    unreadable.
    """
    try:
        base, key = _config()
        resp = http.request_with_retry(
            "GET",
            f"{base}/rest/v1/{TABLE}"
            f"?section=eq.{section}&select=issue_date,edition,issue_number"
            f"&issue_number=not.is.null&order=issue_number.desc&limit=1",
            label="Supabase",
            headers=_headers(key),
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception as e:  # noqa: BLE001 — a number is not worth failing a run over
        print(f"  ⚠ could not read the last issue number (non-fatal): {e}")
        return 1
    if not rows:
        return 1
    last = rows[0]
    if last["issue_date"] == issue_date and last.get("edition", 1) == edition:
        return int(last["issue_number"])
    return int(last["issue_number"]) + 1


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
