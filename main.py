#!/usr/bin/env python3
"""Daily Startup News Summary → Google Calendar.

Scrapes TechCrunch Telegram, generates an AI-powered disruption-focused
summary via OpenAI, and inserts a calendar event at 09:00 KST.
"""

import json
import os
import sys

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

from google.oauth2 import service_account
from googleapiclient.discovery import build
import anthropic

# ── Config ──────────────────────────────────────────────────────────────────
CALENDAR_ID = os.environ.get("CALENDAR_ID", "ad3a712618285ba2a011179683b92bdc10718051482df8d950ccfb95a1f0aa19@group.calendar.google.com")
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GCP_SA_KEY = os.environ["GCP_SA_KEY"]  # JSON string of service account key
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
SUMMARY_PROMPT = """\
You are a startup industry analyst. Based on the following news items from \
TechCrunch's Telegram channel, create a **Daily Startup News Summary**.

For each major story (funding rounds, product launches, strategic \
partnerships, acquisitions), produce:

1. **What happened** – factual summary (2-3 sentences)
2. **Industry status** – current state of the industry being disrupted \
(market size, incumbents, pain points)
3. **Why this is disruptive** – specifically how the startup/company is \
challenging the status quo, what aspect of the industry it is disrupting, \
and why it matters

Group minor stories under **"Other Notable Headlines"** with a one-line \
description each.

Format the output in clean Markdown with headers. Be analytical and specific \
about disruption angles.

Today's date: {today}

--- NEWS ITEMS ---
{news_items}
"""


def generate_summary(news_items: list[dict]) -> str:
    """Call Anthropic Claude to produce the disruption-focused summary."""
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
    return response.content[0].text


# ── Google Calendar ──────────────────────────────────────────────────────────
def get_calendar_service():
    """Build a Calendar API client from the service-account JSON env var."""
    sa_info = json.loads(GCP_SA_KEY)
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=SCOPES
    )
    return build("calendar", "v3", credentials=creds)


def create_calendar_event(summary: str) -> str:
    """Insert a 30-min event at 09:00 KST with the summary as description."""
    service = get_calendar_service()

    now_kst = datetime.now(KST)
    start = now_kst.replace(hour=9, minute=0, second=0, microsecond=0)
    end = start + timedelta(minutes=30)

    event_body = {
        "summary": f"📰 Daily Startup News – {now_kst.strftime('%b %d, %Y')}",
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


# ── Main ─────────────────────────────────────────────────────────────────────
def run():
    print("▸ Scraping TechCrunch Telegram...")
    news_items = scrape_techcrunch_telegram()
    if not news_items:
        print("✗ No news items found.")
        sys.exit(1)
    print(f"  Found {len(news_items)} items.")

    print("▸ Generating AI summary...")
    summary = generate_summary(news_items)

    print("▸ Creating Google Calendar event...")
    event_link = create_calendar_event(summary)
    print(f"✓ Event created: {event_link}")


if __name__ == "__main__":
    run()
