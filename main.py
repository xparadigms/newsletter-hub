#!/usr/bin/env python3
"""Daily Startup News Summary → Google Calendar.

Scrapes TechCrunch Telegram, generates an AI-powered disruption-focused
summary via OpenAI, and inserts a calendar event at 09:00 KST.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
load_dotenv()

import anthropic
import requests
from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ── Config ──────────────────────────────────────────────────────────────────
CALENDAR_ID = os.environ.get("CALENDAR_ID", "ad3a712618285ba2a011179683b92bdc10718051482df8d950ccfb95a1f0aa19@group.calendar.google.com")
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GCP_SA_KEY = os.environ.get("GCP_SA_KEY", "")  # JSON string of service account key
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.environ.get(
    "NOTION_DATABASE_ID",
    "3555bc953df380e2ae70df4401216aee",
)
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Seoul")
TELEGRAM_URL = "https://t.me/s/techcrunchcom"
SCOPES = ["https://www.googleapis.com/auth/calendar"]
KST = timezone(timedelta(hours=9))


# ── Scraper ─────────────────────────────────────────────────────────────────
def scrape_techcrunch_telegram() -> list[dict]:
    """Fetch the latest posts from the TechCrunch Telegram public page."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(TELEGRAM_URL, headers=headers, timeout=30)
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

        if text:
            items.append({"text": text, "url": url, "date": date_str})

    return items


# ── LLM Summary ─────────────────────────────────────────────────────────────
ISSUE_NUMBER = int(os.environ.get("ISSUE_NUMBER", "1"))

SUMMARY_PROMPT = """\
You are a startup industry analyst. Based on the following news items from \
TechCrunch's Telegram channel, create a Daily Startup News Summary.

First line MUST be:
MAIN_TITLE: [concise English title of the single most important story, ≤8 words]

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

Example format:

━━━━━━━━━━━━━━━━━━━━
💰 COMPANY NAME — $XXM Series X at $XB Valuation
━━━━━━━━━━━━━━━━━━━━

▸ What happened
  Brief 2-3 sentence summary here.

▸ Industry status
  Brief industry context here.

▸ Why this is disruptive
  Brief disruption analysis here.


Today's date: {today}

--- NEWS ITEMS ---
{news_items}
"""


def generate_summary(news_items: list[dict]) -> tuple[str, str]:
    """Call Anthropic Claude to produce the disruption-focused summary.

    Returns (main_title, summary_text).
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    formatted = "\n\n".join(
        f"- {item['text']}\n  URL: {item['url']}\n  Date: {item['date']}"
        for item in news_items
    )
    today_str = datetime.now(KST).strftime("%B %d, %Y")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        system="You are a senior startup and venture capital analyst.",
        messages=[
            {
                "role": "user",
                "content": SUMMARY_PROMPT.format(
                    today=today_str, news_items=formatted
                ),
            },
        ],
    )
    raw = response.content[0].text

    # Extract the MAIN_TITLE line
    main_title = "Startup News"
    lines = raw.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("MAIN_TITLE:"):
            main_title = line[len("MAIN_TITLE:"):].strip().strip('"').strip("'")
            body_start = i + 1
            break

    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    summary_text = "\n".join(lines[body_start:])

    return main_title, summary_text


# ── Google Calendar ──────────────────────────────────────────────────────────
def get_calendar_service():
    """Build a Calendar API client from the service-account JSON env var."""
    sa_info = json.loads(GCP_SA_KEY)
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=SCOPES
    )
    return build("calendar", "v3", credentials=creds)


def _issue_title(main_title: str) -> str:
    """Format the standard [Startup News #NN] (main_title) title string."""
    return f"[Startup News #{ISSUE_NUMBER}] ({main_title})"


def create_calendar_event(summary: str, main_title: str = "Startup News") -> str:
    """Insert a 30-min event at 09:00 KST with the summary as description."""
    service = get_calendar_service()

    now_kst = datetime.now(KST)
    start = now_kst.replace(hour=9, minute=0, second=0, microsecond=0)
    end = start + timedelta(minutes=30)

    event_body = {
        "summary": _issue_title(main_title),
        "description": summary,
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": TIMEZONE,
        },
        "end": {
            "dateTime": end.isoformat(),
            "timeZone": TIMEZONE,
        },
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": 0}],
        },
    }

    event = (
        service.events()
        .insert(calendarId=CALENDAR_ID, body=event_body)
        .execute()
    )
    return event.get("htmlLink", "")


# ── Notion ───────────────────────────────────────────────────────────────────
NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"

_SECTION_HEADERS = ["MAJOR STORIES", "OTHER NOTABLE HEADLINES", "OTHER NOTABLE", "OTHER HEADLINES"]
_SUB_HEADERS = ["▸ What happened", "▸ Industry status", "▸ Why this is disruptive"]


def _rt(content: str, bold: bool = False) -> dict:
    """Build a Notion rich-text object."""
    obj = {"type": "text", "text": {"content": content[:2000]}}
    if bold:
        obj["annotations"] = {"bold": True}
    return obj


def _text_to_notion_blocks(text: str) -> list[dict]:
    """Convert the newsletter plain text into well-structured Notion blocks."""
    blocks = []
    for line in text.split("\n"):
        stripped = line.strip()

        if not stripped or stripped.startswith("DAILY STARTUP NEWS SUMMARY"):
            continue

        # Dividers
        if "━" in stripped and stripped.count("━") >= 5:
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            continue

        # Section headers → H2 blue
        if stripped in _SECTION_HEADERS:
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
        if re.match(r'^[💰🤝🛒🚀🏷️]\s', stripped):
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

        # Sub-headers (▸ What happened) → bold
        if stripped in _SUB_HEADERS:
            label = stripped.replace("▸ ", "")
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [_rt(f"▸ {label}", bold=True)]},
            })
            continue

        # Bullet points → bulleted list
        if stripped.startswith("▸"):
            content = stripped.lstrip("▸ ").strip()
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [_rt(content)]},
            })
            continue

        # Sub-bullets
        if stripped.startswith("└─"):
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


def create_notion_page(summary: str, main_title: str = "Startup News") -> str:
    """Create a Notion page in the newsletter database with the summary."""
    if not NOTION_TOKEN:
        print("  ⚠ NOTION_TOKEN not set, skipping Notion.")
        return ""

    now_kst = datetime.now(KST)
    title = _issue_title(main_title)

    all_blocks = _text_to_notion_blocks(summary)
    date_str = now_kst.strftime("%Y-%m-%d")

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

    # Append remaining blocks in batches of 100 if needed
    for i in range(100, len(all_blocks), 100):
        batch = all_blocks[i:i + 100]
        append_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        r = requests.patch(append_url, headers=headers, json={"children": batch}, timeout=30)
        r.raise_for_status()

    return page.get("url", "")


# ── Main ─────────────────────────────────────────────────────────────────────
def run():
    print("▸ Scraping TechCrunch Telegram...")
    news_items = scrape_techcrunch_telegram()
    if not news_items:
        print("✗ No news items found.")
        sys.exit(1)
    print(f"  Found {len(news_items)} items.")

    print("▸ Generating AI summary...")
    main_title, summary = generate_summary(news_items)
    print(f"  Title: [Startup News #{ISSUE_NUMBER}] ({main_title})")

    if CALENDAR_ID and GCP_SA_KEY:
        try:
            print("▸ Creating Google Calendar event...")
            event_link = create_calendar_event(summary, main_title)
            print(f"✓ Event created: {event_link}")
        except Exception as e:
            print(f"  ⚠ Calendar failed (non-fatal): {e}")
    else:
        print("  ⚠ CALENDAR_ID or GCP_SA_KEY not set, skipping Calendar.")

    print("▸ Saving to Notion...")
    notion_url = create_notion_page(summary, main_title)
    if notion_url:
        print(f"✓ Notion page created: {notion_url}")


if __name__ == "__main__":
    run()
