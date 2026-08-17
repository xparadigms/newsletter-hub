#!/usr/bin/env python3
"""Standalone script to add furigana toggles to the latest Japan Briefing page.

The same logic runs automatically at the end of every ``python main.py`` issue
generation.  Use this script to retro-fit furigana onto an already-published
page without regenerating the issue.
"""

import os
import sys

import requests

for _key in ("NOTION_TOKEN", "ANTHROPIC_API_KEY"):
    if _key not in os.environ:
        print(f"\u2717 {_key} is not set. Export it or source .env.local first.")
        sys.exit(1)

from main import (  # noqa: E402
    NOTION_DATABASE_ID,
    NOTION_TOKEN,
    NOTION_VERSION,
    add_furigana_to_page,
)


def find_latest_page() -> str:
    """Query the database for the most recent page and return its ID."""
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    payload = {
        "sorts": [{"property": "Date", "direction": "descending"}],
        "page_size": 1,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    results = r.json()["results"]
    if not results:
        print("\u2717 No pages found in the database.")
        sys.exit(1)
    page = results[0]
    title = "".join(t["plain_text"] for t in page["properties"]["Name"]["title"])
    print(f"  Page: {title}")
    return page["id"]


if __name__ == "__main__":
    print("\u25b8 Finding latest Japan Briefing page...")
    page_id = find_latest_page()
    count = add_furigana_to_page(page_id)
    print(f"\u2713 Done \u2014 {count} furigana toggles inserted.")
