#!/usr/bin/env python3
"""Recover a Rails issue from its Google Calendar event into Notion.

When the Notion write fails but the Calendar event was already created, the
generated issue text survives only in that event's description. This script
reads it back out and creates the Notion page that should have existed, so a
failed run can be repaired without regenerating different content (and without
creating a duplicate Calendar event).

Environment (same secrets as the daily workflow):
    ANTHROPIC_API_KEY, GCP_SA_KEY, NOTION_TOKEN,
    CALENDAR_ID, NOTION_DATABASE_ID, ISSUE_NUMBER

ISSUE_NUMBER must match the issue you are repairing, since it determines both
the event title that is searched for and the Notion page title.

Usage:
    ISSUE_NUMBER=102 python backfill.py             # dry run
    ISSUE_NUMBER=102 python backfill.py --commit    # write to Notion
"""
import argparse
import sys
from datetime import datetime, timedelta

import main


def find_event(service, issue_number: str, lookback_days: int):
    """Return the Calendar event for the given issue number, or None."""
    now_kst = datetime.now(main.KST)
    lo = (now_kst - timedelta(days=lookback_days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    hi = now_kst + timedelta(days=1)

    events = (
        service.events()
        .list(
            calendarId=main.CALENDAR_ID,
            timeMin=lo.isoformat(),
            timeMax=hi.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
        .get("items", [])
    )

    print(f"▸ {len(events)} calendar event(s) in the last {lookback_days} day(s):")
    for e in events:
        start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date", "?")
        desc_len = len(e.get("description") or "")
        print(f"   - {start}  {e.get('summary', '(no title)')}  [{desc_len} chars]")

    prefix = f"[Finance Infra #{issue_number}]"
    return next(
        (e for e in events if (e.get("summary") or "").startswith(prefix)), None
    ), prefix


def notion_has_issue(prefix: str) -> bool:
    """True if a page whose title starts with `prefix` already exists."""
    resp = main._notion_request(
        "POST",
        f"https://api.notion.com/v1/databases/{main.NOTION_DATABASE_ID}/query",
        headers={
            "Authorization": f"Bearer {main.NOTION_TOKEN}",
            "Notion-Version": main.NOTION_VERSION,
            "Content-Type": "application/json",
        },
        json={"page_size": 50},
    )
    resp.raise_for_status()

    titles = []
    for row in resp.json().get("results", []):
        title_prop = row.get("properties", {}).get("Name", {}).get("title", [])
        titles.append("".join(t.get("plain_text", "") for t in title_prop))

    print(f"▸ {len(titles)} recent page(s) in the Notion DB:")
    for t in titles[:10]:
        print(f"   - {t}")

    return any(t.startswith(prefix) for t in titles)


def main_title_from_summary(summary: str) -> str:
    """Recover 'Some Title' from '[Finance Infra #102] (Some Title)'."""
    s = summary.rstrip()
    if "(" in s and s.endswith(")"):
        return s[s.index("(") + 1 : s.rindex(")")]
    return "Finance Infra"


def run() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--commit", action="store_true",
        help="actually create the Notion page (default is a dry run)",
    )
    ap.add_argument(
        "--lookback-days", type=int, default=3,
        help="how far back to search the calendar (default: 3)",
    )
    args = ap.parse_args()

    issue_number = str(main.ISSUE_NUMBER)
    print(f"▸ Repairing issue #{issue_number}")
    print(f"▸ Target Notion DB: {main.NOTION_DATABASE_ID}")

    if not main.NOTION_TOKEN:
        print("✗ NOTION_TOKEN is not set.")
        return 1
    if not main.GCP_SA_KEY or main.GCP_SA_KEY.strip() in ("", "{}"):
        print("✗ GCP_SA_KEY is not set; cannot read the Calendar event.")
        return 1

    service = main.get_calendar_service()
    event, prefix = find_event(service, issue_number, args.lookback_days)

    if not event:
        print(f"\n✗ No calendar event found starting with '{prefix}'.")
        return 1

    summary = event["summary"]
    issue_text = event.get("description") or ""
    if not issue_text.strip():
        print(f"\n✗ Event '{summary}' has an empty description; nothing to recover.")
        return 1

    title = main_title_from_summary(summary)
    blocks = main._text_to_notion_blocks(issue_text)
    print(f"\n✓ Matched event: {summary}")
    print(f"  Issue text: {len(issue_text)} chars → {len(blocks)} Notion blocks")
    print(f"  Recovered title: {title!r}")

    if notion_has_issue(prefix):
        print(f"\n✓ Issue #{issue_number} is already in Notion — nothing to do.")
        return 0

    if not args.commit:
        print("\n── DRY RUN ── re-run with --commit to create the Notion page.")
        return 0

    print("\n▸ Creating Notion page...")
    url, page_id = main.create_notion_page(issue_text, title)
    print(f"✓ Notion page created: {url}")

    if page_id:
        try:
            main.add_furigana_to_page(page_id)
        except Exception as e:
            print(f"  ⚠ Furigana step failed (non-fatal): {e}")

    print("\n✓ Backfill complete.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
