#!/usr/bin/env python3
"""One-time script: backfill the 3 most recent days of TechCrunch news to Notion."""

import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
load_dotenv()

import anthropic
import requests
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "3555bc953df380e2ae70df4401216aee")

TELEGRAM_URL = "https://t.me/s/techcrunchcom"
NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

SUMMARY_PROMPT = """\
You are a startup industry analyst. Based on the following news items from \
TechCrunch's Telegram channel, create a Daily Startup News Summary.

For each major story (funding rounds, product launches, strategic \
partnerships, acquisitions), produce:

• What happened – factual summary (2-3 sentences)
• Industry status – current state of the industry being disrupted \
(market size, incumbents, pain points)
• Why this is disruptive – specifically how the startup/company is \
challenging the status quo, what aspect of the industry it is disrupting, \
and why it matters

Group minor stories under an "Other Notable Headlines" section with a \
one-line description each.

⚠️ CRITICAL FORMATTING RULES — this text will be displayed inside a Google \
Calendar event description, which is PLAIN TEXT only:
- Do NOT use Markdown (no #, ##, ###, **, *, ```, etc.)
- Use these Unicode characters for visual structure:
  • Use ━━━━━━━━━━━━━━━━━━━━ as section dividers
  • Use ALL CAPS for section headers (e.g. MAJOR STORIES, OTHER HEADLINES)
  • Use ▸ for bullet points
  • Use └─ for sub-bullets
  • Use 🏷️ emojis to tag categories: 💰 Funding, 🤝 Partnership, 🛒 Acquisition, 🚀 Launch
  • Use blank lines between sections for readability
- Keep each story's analysis concise (3-5 lines per section)
- Be analytical and specific about disruption angles.

Today's date: {today}

--- NEWS ITEMS ---
{news_items}
"""

_SECTION_HEADERS = [
    "MAJOR STORIES", "OTHER HEADLINES", "OTHER NOTABLE",
    "FUNDING", "PARTNERSHIP", "ACQUISITION", "LAUNCH",
    "WHAT HAPPENED", "INDUSTRY STATUS", "WHY THIS IS DISRUPTIVE",
]


def _rich_text(content):
    return {"type": "text", "text": {"content": content[:2000]}}


def _is_section_header(line):
    stripped = line.strip()
    if not stripped:
        return False
    return any(h in stripped.upper() for h in _SECTION_HEADERS)


def _is_divider(line):
    return "━" in line and line.strip().count("━") >= 5


def _text_to_notion_blocks(text):
    blocks = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if _is_divider(stripped):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            continue
        if _is_section_header(stripped):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [_rich_text(stripped)],
                    "color": "blue_background",
                    "is_toggleable": False,
                },
            })
            continue
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [_rich_text(stripped)]},
        })
    return blocks


def scrape_telegram():
    resp = requests.get(TELEGRAM_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    for widget in soup.select("div.tgme_widget_message_wrap"):
        text_el = widget.select_one("div.tgme_widget_message_text")
        if not text_el:
            continue
        text = text_el.get_text(separator=" ", strip=True)
        link_el = text_el.select_one('a[href*="techcrunch.com"]')
        url = link_el["href"] if link_el else ""
        date_el = widget.select_one("time[datetime]")
        date_str = date_el["datetime"] if date_el else ""
        if text and date_str:
            items.append({"text": text, "url": url, "date": date_str})
    return items


def group_by_day(items):
    by_day = defaultdict(list)
    for item in items:
        try:
            dt = datetime.fromisoformat(item["date"].replace("Z", "+00:00"))
            day_key = dt.astimezone(KST).strftime("%Y-%m-%d")
        except Exception:
            continue
        by_day[day_key].append(item)
    return dict(sorted(by_day.items(), reverse=True))


def generate_summary(news_items, date_str):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    formatted = "\n\n".join(
        f"- {item['text']}\n  URL: {item['url']}\n  Date: {item['date']}"
        for item in news_items
    )
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    today_str = dt.strftime("%B %d, %Y")

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system="You are a senior startup and venture capital analyst.",
        messages=[{"role": "user", "content": SUMMARY_PROMPT.format(today=today_str, news_items=formatted)}],
    )
    return response.content[0].text


def create_notion_page(summary, date_str):
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    title = f"📰 Daily Startup News – {dt.strftime('%b %d, %Y')}"

    all_blocks = _text_to_notion_blocks(summary)

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": date_str}},
        },
        "children": all_blocks[:100],
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

    for i in range(100, len(all_blocks), 100):
        batch = all_blocks[i:i + 100]
        append_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        r = requests.patch(append_url, headers=headers, json={"children": batch}, timeout=30)
        r.raise_for_status()

    return page.get("url", "")


def main():
    print("▸ Scraping TechCrunch Telegram...")
    items = scrape_telegram()
    print(f"  Found {len(items)} items total.")

    by_day = group_by_day(items)
    days = list(by_day.keys())[:3]
    print(f"  3 most recent days: {days}")

    for date_str in days:
        day_items = by_day[date_str]
        print(f"\n▸ [{date_str}] {len(day_items)} items — generating summary...")
        summary = generate_summary(day_items, date_str)

        print(f"  Saving to Notion...")
        url = create_notion_page(summary, date_str)
        print(f"  ✓ {url}")

    print("\n✓ Done — 3 newsletters backfilled to Notion.")


if __name__ == "__main__":
    main()
