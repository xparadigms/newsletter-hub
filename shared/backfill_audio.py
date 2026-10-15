"""Voice the issues that were published without audio.

    python -m shared.backfill_audio --since 2026-10-01 [--dry-run]

attach_audio is non-fatal by design, so when the speech service fails an issue
still publishes — silently. This walks every published issue since a date,
voices each sentence that has no clip, and writes the blocks back. Sentences
that already have audio are left alone, so it is safe to run again.

Needs SUPABASE_URL and SUPABASE_SECRET_KEY; SITE_URL and REVALIDATE_SECRET to
refresh the site's copy of each issue it touches.
"""

from __future__ import annotations

import argparse

from . import audio, http, store

# The Chinese sections read pinyin blocks; every other section reads its
# Japanese paragraphs (sections without any simply have nothing to voice).
ZH = {"china", "mandarin"}


def _fetch(since: str) -> list[dict]:
    base, key = store._config()
    resp = http.request_with_retry(
        "GET",
        f"{base}/rest/v1/{store.TABLE}?issue_date=gte.{since}&published=eq.true"
        "&select=section,slug,run_key,blocks&order=issue_date.asc",
        label="Supabase",
        headers=store._headers(key),
    )
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", required=True, help="YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = _fetch(args.since)
    print(f"{len(rows)} published issue(s) since {args.since}")
    written = 0
    for row in rows:
        blocks = row["blocks"]
        before = sum(1 for b in blocks if b.get("audio"))
        print(f"• {row['section']}/{row['slug']} — {before} clip(s) already")
        if args.dry_run:
            continue
        try:
            audio.attach_audio(blocks, "zh" if row["section"] in ZH else "ja")
        except Exception as e:  # noqa: BLE001 — one issue must not stop the rest
            print(f"  ⚠ audio failed: {e}")
            continue
        after = sum(1 for b in blocks if b.get("audio"))
        if after == before:
            continue
        store.patch_issue(row["run_key"], {"blocks": blocks})
        store.ping_revalidate(row["section"], row["slug"])
        written += 1
        print(f"  ✓ {after - before} clip(s) added")
    print(f"\n{written} issue(s) updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
