"""Give every published issue without one a cover.

    python -m shared.backfill_covers [--dry-run] [--limit N] [--redo-library]

Safe to rerun: only rows whose cover is still null are touched — or, with
--redo-library, also those whose cover came from the photo library, to pick
them again after a change to how photos are searched. See
shared/covers.py for where the images come from.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor

from . import covers, http, store


def _fetch(redo_library: bool = False) -> list[dict]:
    base, key = store._config()
    rows: list[dict] = []
    while True:
        resp = http.request_with_retry(
            "GET",
            f"{base}/rest/v1/{store.TABLE}?"
            + ("or=(cover.is.null,cover->>kind.eq.openverse)" if redo_library else "cover=is.null")
            + "&published=eq.true"
            f"&select=section,slug,run_key,title,blocks&order=issue_date.desc&limit=200&offset={len(rows)}",
            label="Supabase",
            headers=store._headers(key),
        )
        resp.raise_for_status()
        page = resp.json()
        rows += page
        if len(page) < 200:
            return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--redo-library", action="store_true")
    args = parser.parse_args()

    rows = _fetch(args.redo_library)
    if args.limit:
        rows = rows[: args.limit]
    print(f"{len(rows)} issue(s) to cover")

    def one(row: dict) -> tuple[dict, dict | None]:
        try:
            return row, covers.find_cover(row)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ {row['slug']}: {e}")
            return row, None

    found = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for row, cover in pool.map(one, rows):
            label = f"{row['section']}/{row['slug'][:48]}"
            if not cover:
                print(f"  – {label}: none")
                continue
            found += 1
            print(f"  ✓ {label}: {cover['kind']} · {cover.get('via', '')}: {cover.get('query', '')} · {cover['credit']}")
            if not args.dry_run:
                store.patch_issue(row["run_key"], {"cover": cover})
    print(f"\n{found}/{len(rows)} covered{' (dry run)' if args.dry_run else ''}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
