#!/usr/bin/env python3
"""Weekly Watch Newsletter → Calendar + Trilingual Notion.

Pulls the past week of horology/watch-industry news from watch-media RSS feeds,
generates an AI-powered weekly recap, converts it into a trilingual (EN/JP/KR)
edition, inserts a Google Calendar event with the trilingual text as plain-text
description, and creates a trilingual Notion page with furigana toggles and
Korean callouts.

Format mirrors ../startup-newsletter; source is watch RSS instead of Telegram.
"""

from __future__ import annotations

import os
import pathlib
import re
import sys
import json
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
load_dotenv()

import anthropic
import feedparser
import requests
from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build

# The workflow runs with this project as the working directory, so the repo
# root is not importable. Python only puts the *script's* directory on sys.path.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from shared import issue as issue_row, store  # noqa: E402
from shared.http import request_with_retry  # noqa: E402
from shared.trilingual import md_to_blocks as trilingual_to_blocks  # noqa: E402

# ── Config ──────────────────────────────────────────────────────────────────
CALENDAR_ID = os.environ.get(
    "CALENDAR_ID",
    "ad3a712618285ba2a011179683b92bdc10718051482df8d950ccfb95a1f0aa19@group.calendar.google.com",
)
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GCP_SA_KEY = os.environ.get("GCP_SA_KEY", "")  # inline JSON (CI); may be empty locally
GCP_SA_KEY_FILE = os.environ.get("GCP_SA_KEY_FILE", "")  # optional path to key file
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.environ.get(
    "NOTION_DATABASE_ID", "3965bc953df381bbb5ece93744153a6a"
)
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Seoul")
SCOPES = ["https://www.googleapis.com/auth/calendar"]
KST = timezone(timedelta(hours=9))
ISSUE_NUMBER = int(os.environ.get("ISSUE_NUMBER", "1"))
# An extra issue for a day that already has one, requested from the site. The
# scheduled run is edition 1 and its run_key is unchanged, so nothing about the
# daily path moves.
EDITION = int(os.environ.get("EDITION", "1"))


# Watch-media RSS feeds (luxury / mechanical horology).
RSS_FEEDS = {
    "Hodinkee": "https://www.hodinkee.com/articles.rss",
    "Fratello": "https://www.fratellowatches.com/feed/",
    "Monochrome": "https://monochrome-watches.com/feed/",
    "aBlogtoWatch": "https://www.ablogtowatch.com/feed/",
    "WatchPro": "https://www.watchpro.com/feed/",
    "Watches by SJX": "https://watchesbysjx.com/feed/",
    "Worn & Wound": "https://wornandwound.com/feed/",
    "Time+Tide": "https://timeandtidewatches.com/feed/",
    "Quill & Pad": "https://quillandpad.com/feed/",
    "Revolution": "https://revolutionwatch.com/feed/",
}

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
WINDOW_DAYS = 8          # how far back a "week" of news reaches
MAX_ITEMS = 60           # cap items sent to the LLM


# ── Scraper: RSS feeds ──────────────────────────────────────────────────────
def _clean(html_or_text: str) -> str:
    """Strip HTML tags/entities from an RSS summary and collapse whitespace."""
    if not html_or_text:
        return ""
    text = BeautifulSoup(html_or_text, "html.parser").get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text)[:600]


def _entry_dt(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def scrape_rss_feeds() -> list[dict]:
    """Fetch recent watch articles from the configured RSS feeds.

    Collects entries from the past WINDOW_DAYS; if that yields too few, relaxes
    the date filter and takes the latest entries per feed instead.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    recent, fallback, seen = [], [], set()

    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url, agent=UA)
        except Exception as e:
            print(f"  ⚠ Failed to parse {source}: {e}")
            continue

        for entry in feed.entries[:25]:
            link = getattr(entry, "link", "")
            if link and link in seen:
                continue
            title = getattr(entry, "title", "").strip()
            if not title:
                continue
            if link:
                seen.add(link)

            published = _entry_dt(entry)
            summary = _clean(getattr(entry, "summary", ""))
            item = {
                "source": source,
                "text": f"{title}. {summary}" if summary else title,
                "url": link,
                "date": published.isoformat() if published else "",
            }
            if published and published >= cutoff:
                recent.append(item)
            else:
                fallback.append(item)

    items = recent if len(recent) >= 6 else (recent + fallback)
    return items[:MAX_ITEMS]


# ── LLM: weekly English summary ─────────────────────────────────────────────
SUMMARY_PROMPT = """\
You are a watch-industry analyst. Based on the following horology news items \
from the past week, write a Weekly Watch Briefing covering luxury and \
mechanical watches — new releases, brand & business moves, auctions & the \
secondary market, and notable collaborations.

First line MUST be:
MAIN_TITLE: [concise English title of the single most important story of the week, ≤8 words]

For each major story, produce:

▸ What happened – factual summary (2-3 sentences)
▸ The context – where this sits in the market (brand, model line, price, \
history, comparable references)
▸ Why it matters – significance for collectors, enthusiasts, or the trade

Group smaller items under an "OTHER NOTABLE HEADLINES" section with a one-line \
description each.

⚠️ CRITICAL FORMATTING RULES — this text is an intermediate that will be \
translated; keep it PLAIN TEXT (no Markdown: no #, ##, **, *, ```):
- Use ━━━━━━━━━━━━━━━━━━━━ as section dividers
- Use ALL CAPS for section headers (e.g. THIS WEEK'S STORIES, OTHER NOTABLE HEADLINES)
- Use ▸ for the sub-section labels above
- Tag each story header with a category emoji: ⌚ Release, 🏭 Brand/Business, \
💰 Auction/Market, 🤝 Collaboration
- Blank lines between sections; keep each sub-section to 3-5 lines
- Be specific: name brands, references, calibers, prices, and figures.

Example story header:
━━━━━━━━━━━━━━━━━━━━
⌚ BRAND MODEL — short descriptor
━━━━━━━━━━━━━━━━━━━━

This week: {today}

--- NEWS ITEMS ---
{news_items}
"""


def generate_summary(news_items: list[dict]) -> tuple[str, str]:
    """Call Claude to produce the weekly English recap. Returns (main_title, body)."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    formatted = "\n\n".join(
        f"[{item['source']}] {item['text']}\n  URL: {item['url']}\n  Date: {item['date']}"
        for item in news_items
    )
    today_str = datetime.now(KST).strftime("%B %d, %Y")

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system="You are a senior watch-industry analyst and journalist.",
        messages=[
            {"role": "user", "content": SUMMARY_PROMPT.format(today=today_str, news_items=formatted)},
        ],
    )
    raw = response.content[0].text

    main_title = "Watch Weekly"
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


# ── LLM: trilingual conversion ──────────────────────────────────────────────
TRILINGUAL_PROMPT = """\
You are a trilingual (English/Japanese/Korean) watch newsletter editor.

Convert the English newsletter below into a trilingual edition in Notion-flavoured \
Markdown. Follow the structure and rules EXACTLY.

Do NOT add a top-level title — the title is handled separately.

PER-STORY STRUCTURE (repeat for every major story):

### 【日本語の見出し】
(한국어 부제목)
*English headline*

Then for each sub-section (▸ What happened / ▸ The context / ▸ Why it matters):

▸ [English label]

[English paragraph — keep unchanged from source]

[Japanese translation]

<details>
<summary>ふりがな（ひらがな）</summary>
\t[furigana version — keep all kanji, add reading in （） after each kanji word]
</details>

<callout icon="📝">
\t한국어 번역
</callout>
[Korean translation]

After each story add:
왜 중요한가: [1-2 sentences in Korean on why this matters for watch collectors, enthusiasts, or the trade]

Then add --- divider between stories.

FURIGANA RULES:
1. Keep all kanji in place, add reading in parentheses after each kanji word: \
自動巻（じどうま）き, 文字盤（もじばん）
2. Leave katakana, numbers, Latin letters, punctuation unchanged.
3. Handle okurigana correctly: 手巻（てま）き, 基（もと）づく
4. Indent furigana text one tab inside the toggle.
5. Do NOT add furigana to headings or 【…】 lines.

FOR BULLET-LIST SECTIONS ("OTHER NOTABLE HEADLINES" etc.):
Each bullet as:
- **English headline**
Japanese（with inline furigana）
Korean

No toggle needed for single-line headlines.

CLOSING SECTION — add at the very end:
## 今週の表現 / 이번 주 표현

Pick one useful Japanese watch/business term from the issue:
**[term（reading）]**
- 読み方: [hiragana]
- 意味: [Korean meaning]
- 例文: [example sentence]

<details>
<summary>ふりがな</summary>
\t[furigana version of example]
</details>

- メモ: [one-line usage note]

TONE:
- Japanese: clean journalistic newsletter (です/ます or だ/である, match source register)
- Korean: natural, concise, watch-savvy reader
- Currency: $10,000 → 1万ドル (JP) / 1만 달러 (KR). Keep English figure in English layer.

--- ENGLISH NEWSLETTER TO CONVERT ---
{english_summary}
"""


def generate_trilingual(english_summary: str) -> str:
    """Convert the English weekly recap into trilingual Notion Markdown."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        system="You are an expert trilingual (EN/JP/KR) watch newsletter editor.",
        messages=[
            {"role": "user", "content": TRILINGUAL_PROMPT.format(english_summary=english_summary)},
        ],
    )
    return response.content[0].text


# ── Google Calendar ──────────────────────────────────────────────────────────
# Candidate on-disk locations for the service-account key (local-dev fallback,
# only used when GCP_SA_KEY env JSON is not provided — e.g. outside CI).
_SA_KEY_CANDIDATES = [
    GCP_SA_KEY_FILE,
    os.path.join(os.path.dirname(__file__), "..", "rize", "service-account-key.json"),
    os.path.join(os.path.dirname(__file__), "..", "..", "rize", "service-account-key.json"),
]


def _load_gcp_sa_info() -> dict | None:
    """Resolve the service-account key from env JSON, GCP_SA_KEY_FILE, or a known path."""
    raw = os.environ.get("GCP_SA_KEY", "").strip()
    if raw:
        return json.loads(raw)
    for path in _SA_KEY_CANDIDATES:
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    return None


def get_calendar_service():
    """Build a Calendar API client from the resolved service-account credentials."""
    sa_info = _load_gcp_sa_info()
    if not sa_info:
        raise RuntimeError("No GCP service-account key (set GCP_SA_KEY or GCP_SA_KEY_FILE)")
    creds = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    return build("calendar", "v3", credentials=creds)


def _issue_title(main_title: str) -> str:
    """Format the standard [Watch Weekly #NN] (main_title) title string."""
    return f"[Watch Weekly #{ISSUE_NUMBER}] ({main_title})"


def create_calendar_event(description: str, main_title: str = "Watch Weekly") -> str:
    """Insert a 30-min event at 09:00 KST with the trilingual text as description."""
    service = get_calendar_service()

    now_kst = datetime.now(KST)
    start = now_kst.replace(hour=9, minute=0, second=0, microsecond=0)
    end = start + timedelta(minutes=30)

    event_body = {
        "summary": _issue_title(main_title),
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]},
    }
    event = service.events().insert(calendarId=CALENDAR_ID, body=event_body).execute()
    return event.get("htmlLink", "")


# ── Trilingual → Calendar plain text ─────────────────────────────────────────
# Google Calendar descriptions are plain text, so the Notion-flavoured trilingual
# Markdown (### headings, <details> furigana toggles, <callout> Korean blocks,
# --- dividers, **bold**/*italic*) is converted into a clean EN → JP →
# "📝 한국어 번역:" → KR layout. Furigana toggles are dropped (a Notion-only aid).
_INLINE_EMPHASIS_RE = re.compile(r"\*\*(.+?)\*\*|\*(.+?)\*")
_CAL_DIVIDER = "━" * 20


def _strip_inline_md(text: str) -> str:
    """Remove **bold** / *italic* markers, keeping the inner text."""
    return _INLINE_EMPHASIS_RE.sub(lambda m: m.group(1) or m.group(2), text)


def _trilingual_to_calendar_text(md_text: str) -> str:
    """Convert trilingual Notion Markdown into plain text for a Calendar event."""
    lines = md_text.split("\n")
    out: list[str] = []
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()

        # Drop furigana <details> toggles entirely (Notion-only reading aid).
        if stripped.startswith("<details"):
            if "</details>" not in stripped:
                i += 1
                while i < len(lines) and "</details>" not in lines[i]:
                    i += 1
            i += 1
            continue

        # Unwrap <callout> … </callout> → "📝 한국어 번역:" marker line.
        if stripped.startswith("<callout"):
            inner: list[str] = []
            if "</callout>" in stripped:
                body = re.sub(r"<callout[^>]*>", "", stripped)
                body = body.replace("</callout>", "").strip()
                if body and body != "한국어 번역":
                    inner.append(_strip_inline_md(body))
                i += 1
            else:
                i += 1
                while i < len(lines) and lines[i].strip() != "</callout>":
                    s = lines[i].strip()
                    if s and s != "한국어 번역":
                        inner.append(_strip_inline_md(s))
                    i += 1
                i += 1  # skip closing </callout>
            out.append("📝 한국어 번역:")
            out.extend(inner)
            continue

        # Stray tag lines → skip.
        if stripped.startswith("<summary") or stripped == "</details>":
            i += 1
            continue

        # --- dividers → plain-text ━━━━ divider.
        if stripped == "---":
            out.extend(["", _CAL_DIVIDER, ""])
            i += 1
            continue

        # Headings (#, ##, ###) → strip markers, keep the text.
        if stripped.startswith("#"):
            out.append(_strip_inline_md(stripped.lstrip("#").strip()))
            i += 1
            continue

        # Bullet list items "- …" → "▸ …".
        if stripped.startswith("- "):
            out.append("▸ " + _strip_inline_md(stripped[2:].strip()))
            i += 1
            continue

        # Everything else → plain line with inline emphasis stripped.
        out.append(_strip_inline_md(stripped))
        i += 1

    # Collapse runs of blank lines into a single blank line.
    cleaned: list[str] = []
    blank = 0
    for line in out:
        if line.strip():
            blank = 0
            cleaned.append(line)
        else:
            blank += 1
            if blank <= 1:
                cleaned.append("")
    return "\n".join(cleaned).strip()


# ── Notion ───────────────────────────────────────────────────────────────────
NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"


def _notion_headers() -> dict:
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def create_notion_page(all_blocks: list, title: str, date_str: str) -> str:
    """Mirror an issue to Notion. Blocks are built by the caller so the same
    list feeds both Supabase and Notion."""
    if not NOTION_TOKEN:
        print("  ⚠ NOTION_TOKEN not set, skipping Notion.")
        return ""

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": date_str}},
        },
        "children": all_blocks[:100],
    }
    headers = _notion_headers()

    resp = request_with_retry(
        "POST", NOTION_API_URL, label="Notion", headers=headers, json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    page = resp.json()
    page_id = page["id"]

    for i in range(100, len(all_blocks), 100):
        batch = all_blocks[i:i + 100]
        r = request_with_retry(
            "PATCH", f"https://api.notion.com/v1/blocks/{page_id}/children",
            label="Notion", headers=headers, json={"children": batch}, timeout=60,
        )
        r.raise_for_status()
        print(f"  Appended blocks {i}–{i + len(batch)}.")

    return page.get("url", "")


# ── Main ─────────────────────────────────────────────────────────────────────
def run():
    print(f"▸ Watch Weekly — Issue #{ISSUE_NUMBER}")

    print("▸ Scraping watch RSS feeds...")
    news_items = scrape_rss_feeds()
    if not news_items:
        print("✗ No news items found.")
        sys.exit(1)
    print(f"  Found {len(news_items)} items.")

    print("▸ Generating English weekly summary...")
    main_title, summary = generate_summary(news_items)
    print(f"  Title: [Watch Weekly #{ISSUE_NUMBER}] ({main_title})")

    # Trilingual first so it feeds BOTH the calendar (plain text) and Notion.
    print("▸ Converting to trilingual (EN/JP/KR)...")
    try:
        trilingual_md = generate_trilingual(summary)
        print("  ✓ Trilingual conversion complete.")
    except Exception as e:
        print(f"  ⚠ Trilingual conversion failed (non-fatal): {e}")
        trilingual_md = ""

    if not trilingual_md:
        print("✗ No trilingual content — nothing to publish.")
        sys.exit(1)

    # Build the blocks once so the same list feeds Supabase and Notion.
    all_blocks = trilingual_to_blocks(trilingual_md)
    print(f"  Parsed {len(all_blocks)} Notion blocks.")

    date_str = datetime.now(KST).strftime("%Y-%m-%d")
    raw_title = _issue_title(main_title)

    # Supabase first: it is what the site reads, so it is the write that must
    # land. Notion and Calendar are mirrors and neither can fail the run.
    print("▸ Saving to Supabase...")
    row = issue_row.build_row(
        section="watch",
        issue_date=date_str,
        raw_title=raw_title,
        notion_blocks=all_blocks,
        source_text=trilingual_md,
        source_format="trilingual_md",
        edition=EDITION,
    )
    stored = store.upsert_issue(row)
    if stored.get("slug"):
        print(f"✓ Stored: watch/{stored['slug']}")

    print("▸ Mirroring to Notion...")
    try:
        notion_url = create_notion_page(all_blocks, raw_title, date_str)
        if notion_url:
            print(f"✓ Notion page created: {notion_url}")
            if stored.get("slug"):
                store.patch_issue(row["run_key"], {"notion_url": notion_url})
    except Exception as e:
        print(f"  ⚠ Notion mirror failed (non-fatal): {e}")

    if CALENDAR_ID and _load_gcp_sa_info():
        try:
            print("▸ Creating Google Calendar event (trilingual EN/JP/KR)...")
            event_link = create_calendar_event(
                _trilingual_to_calendar_text(trilingual_md), main_title
            )
            print(f"✓ Event created: {event_link}")
        except Exception as e:
            print(f"  ⚠ Calendar failed (non-fatal): {e}")
    else:
        print("  ⚠ CALENDAR_ID or GCP_SA_KEY not set, skipping Calendar.")

    if stored.get("slug"):
        store.ping_revalidate("watch", stored["slug"])


if __name__ == "__main__":
    run()
