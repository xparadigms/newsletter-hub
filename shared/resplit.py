"""Split an issue published whole into one article per story, after the fact.

    python -m shared.resplit --section startup --date 2026-09-28 [--dry-run]

For issues published before shared/split.py existed. Uses the same rules the
generators use at publishing time (split.RULES), on the blocks already stored,
so furigana and audio carry over without regenerating anything. The whole
issue is then unpublished rather than deleted: the site stops listing it, and
setting published back to true undoes this.

Business Insight issues from before the split have no English title per
insight, so those are written from the Japanese headlines with one short call.
"""

from __future__ import annotations

import argparse
from typing import Any

from . import http, llm, split, store

TITLE_PROMPT = """\
Each line below is the Japanese headline of one business insight. Write an \
English title for each in 8 words or fewer, in the same order, one per line, \
with nothing else: no numbers, quotes or commentary.

{headlines}
"""


def _fetch(section: str, date: str) -> dict[str, Any] | None:
    base, key = store._config()
    resp = http.request_with_retry(
        "GET",
        f"{base}/rest/v1/{store.TABLE}?run_key=eq.{section}:{date}&select=*",
        label="Supabase",
        headers=store._headers(key),
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


def _business_titles(stories: list[list[dict]]) -> list[str]:
    heads = [split.story_title("business", st) for st in stories]
    try:
        text = llm.complete(
            model="claude-sonnet-4-6",
            system="You write concise English headlines.",
            user=TITLE_PROMPT.format(headlines="\n".join(heads)),
            max_tokens=500,
            label="titles",
        )
        titles = [line.strip() for line in text.splitlines() if line.strip()]
        if len(titles) == len(heads):
            return titles
    except Exception as e:  # noqa: BLE001 — Japanese titles are a fine fallback
        print(f"  ⚠ could not write English titles: {e}")
    return heads


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", required=True, choices=sorted(split.RULES))
    parser.add_argument("--date", required=True, help="issue date, YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    row = _fetch(args.section, args.date)
    if not row:
        print(f"✗ no unsplit issue {args.section}:{args.date}")
        return
    if not row.get("published"):
        print(f"✗ {args.section}:{args.date} is already unpublished, so already split")
        return

    stories, closing = split.split_parts(row["blocks"], **split.RULES[args.section])
    if not stories:
        print("✗ no stories found; leaving the issue as it is")
        return
    titles = (
        _business_titles(stories)
        if args.section == "business"
        else [split.story_title(args.section, st) for st in stories]
    )
    series = (row.get("series") or "").strip() or args.section
    print(f"▸ {row['title']} → {len(stories)} stories under {series}")
    for t in titles:
        print(f"  - {t}")
    if args.dry_run:
        print("(dry run — nothing written)")
        return

    closing_title = split.CLOSING_TITLES.get(args.section)
    split.publish(
        section=args.section,
        issue_date=args.date,
        series=series,
        stories=list(zip(titles, stories)),
        closing=(closing_title, closing) if closing_title else None,
        source_text=row.get("source_text") or "",
        source_format=row.get("source_format") or "plain",
        edition=row.get("edition") or 1,
        fallback=(row["raw_title"], row["blocks"]),
        # Already in the stored blocks.
        audio_lang=None,
    )
    store.patch_issue(row["run_key"], {"published": False})
    print(f"✓ unpublished the whole issue {row['run_key']}")
    store.ping_revalidate(args.section, row["slug"])


if __name__ == "__main__":
    main()
