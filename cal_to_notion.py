#!/usr/bin/env python3
"""Fetch the 7 most recent Daily Startup News events from Google Calendar
and create cleanly formatted Notion pages."""

import json
import os
import re
import time

from dotenv import load_dotenv
load_dotenv()

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ── Config ───────────────────────────────────────────────────────────────────
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "3555bc953df380e2ae70df4401216aee")
CALENDAR_ID = os.environ["CALENDAR_ID"]
SA_KEY_PATH = os.path.join(os.path.dirname(__file__), "..", "rize", "service-account-key.json")

NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"


# ── Google Calendar ──────────────────────────────────────────────────────────
def get_recent_newsletters(n=7):
    """Return the N most recent 'Daily Startup News' calendar events."""
    with open(SA_KEY_PATH) as f:
        sa_info = json.load(f)
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=["https://www.googleapis.com/auth/calendar.readonly"]
    )
    service = build("calendar", "v3", credentials=creds)

    result = service.events().list(
        calendarId=CALENDAR_ID,
        maxResults=200,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])
    startup = [e for e in events if "Daily Startup News" in e.get("summary", "")]
    return startup[-n:]


# ── Text → Notion Blocks (clean formatting) ─────────────────────────────────
def _rt(content, bold=False):
    """Build a Notion rich-text object."""
    obj = {"type": "text", "text": {"content": content[:2000]}}
    if bold:
        obj["annotations"] = {"bold": True}
    return obj


def _is_divider(line):
    return "━" in line and line.strip().count("━") >= 5


def _is_title_line(line):
    """DAILY STARTUP NEWS SUMMARY - DATE"""
    return line.strip().startswith("DAILY STARTUP NEWS SUMMARY")


def _is_section_header(line):
    """ALL CAPS section headers like MAJOR STORIES, OTHER NOTABLE HEADLINES."""
    stripped = line.strip()
    headers = ["MAJOR STORIES", "OTHER NOTABLE HEADLINES", "OTHER NOTABLE", "OTHER HEADLINES"]
    return stripped in headers


def _is_story_header(line):
    """Emoji + company headers like '💰 ANTHROPIC — ...'"""
    stripped = line.strip()
    # Starts with an emoji category marker
    return bool(re.match(r'^[💰🤝🛒🚀🏷️]\s', stripped))


def _is_sub_header(line):
    """▸ What happened / ▸ Industry status / ▸ Why this is disruptive"""
    stripped = line.strip()
    sub_headers = ["▸ What happened", "▸ Industry status", "▸ Why this is disruptive"]
    return stripped in sub_headers


def _is_bullet(line):
    """▸ bullet point (not a sub-header)"""
    return line.strip().startswith("▸") and not _is_sub_header(line)


def _is_sub_bullet(line):
    return line.strip().startswith("└─")


def text_to_notion_blocks(text):
    """Convert newsletter plain text into well-structured Notion blocks."""
    blocks = []

    for line in text.split("\n"):
        stripped = line.strip()

        # Skip empty lines and title line (redundant with page title)
        if not stripped or _is_title_line(stripped):
            continue

        # Dividers
        if _is_divider(stripped):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            continue

        # Section headers → H2 blue background
        if _is_section_header(stripped):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [_rt(stripped)],
                    "color": "blue_background",
                    "is_toggleable": False,
                },
            })
            continue

        # Story headers (💰 COMPANY — ...) → H3
        if _is_story_header(stripped):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [_rt(stripped)],
                    "color": "default",
                    "is_toggleable": False,
                },
            })
            continue

        # Sub-headers (▸ What happened) → bold paragraph
        if _is_sub_header(stripped):
            label = stripped.replace("▸ ", "")
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [_rt(f"▸ {label}", bold=True)]},
            })
            continue

        # Bullet points → bulleted list items
        if _is_bullet(stripped):
            content = stripped.lstrip("▸ ").strip()
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [_rt(content)]},
            })
            continue

        # Sub-bullets
        if _is_sub_bullet(stripped):
            content = stripped.lstrip("└─ ").strip()
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [_rt(f"→ {content}")]},
            })
            continue

        # Everything else → paragraph
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [_rt(stripped)]},
        })

    return blocks


# ── Notion ───────────────────────────────────────────────────────────────────
def create_notion_page(title, date_str, blocks):
    """Create a Notion page with the given blocks."""
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": date_str}},
        },
        "children": blocks[:100],
    }

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    resp = requests.post(NOTION_API_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    page = resp.json()
    page_id = page["id"]

    # Append remaining blocks in batches of 100
    for i in range(100, len(blocks), 100):
        batch = blocks[i:i + 100]
        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        r = requests.patch(url, headers=headers, json={"children": batch}, timeout=30)
        r.raise_for_status()

    return page.get("url", "")


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("▸ Fetching 7 most recent newsletters from Google Calendar...")
    events = get_recent_newsletters(7)
    print(f"  Found {len(events)} events.")

    for event in events:
        title = event.get("summary", "")
        start = event.get("start", {}).get("dateTime", "")
        date_str = start[:10]  # YYYY-MM-DD
        description = event.get("description", "")

        if not description:
            print(f"  ⚠ {date_str} — no description, skipping")
            continue

        blocks = text_to_notion_blocks(description)
        print(f"  [{date_str}] {title} — {len(blocks)} blocks → Notion...", end=" ")

        url = create_notion_page(title, date_str, blocks)
        print(f"✓")

        time.sleep(0.5)  # rate limit courtesy

    print("\n✓ Done — 7 newsletters saved to Notion.")


if __name__ == "__main__":
    main()
