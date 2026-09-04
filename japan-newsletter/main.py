#!/usr/bin/env python3
"""Japan Daily Talk — Daily Japanese newsletter → Supabase, Notion, Calendar.

Scrapes Japan crypto/regulation/real-estate news from Japanese and English
sources, generates a bilingual (JP body + KR translation) issue via Claude,
and inserts a calendar event + Notion page.
"""

import json
import os
import pathlib
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import anthropic
import feedparser
import requests
from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build

# The workflow runs with this project as the working directory, so the repo root
# is not importable. Python only puts the *script's* directory on sys.path.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from shared import audio, furigana, issue as issue_row, plaintext, store  # noqa: E402
from shared.http import request_with_retry  # noqa: E402

# ── Config ──────────────────────────────────────────────────────────────────
CALENDAR_ID = os.environ.get(
    "CALENDAR_ID",
    "ad3a712618285ba2a011179683b92bdc10718051482df8d950ccfb95a1f0aa19@group.calendar.google.com",
)
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GCP_SA_KEY = os.environ.get("GCP_SA_KEY", "")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.environ.get(
    "NOTION_DATABASE_ID",
    "36a5bc953df38036acb4d2b6553e582c",
)
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Seoul")
SCOPES = ["https://www.googleapis.com/auth/calendar"]
KST = timezone(timedelta(hours=9))
JST = timezone(timedelta(hours=9))  # Same offset as KST

ISSUE_NUMBER = int(os.environ.get("ISSUE_NUMBER", "1"))

# ── News Sources (general Japan) ────────────────────────────────────────────
_GNEWS = "https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"

# The floor, as in china-newsletter: the RSS feeds below are a bonus, these
# carry the issue when one of them is down. Picked by measured freshness —
# "日本 政治" returns evergreen analysis and "日本 テクノロジー" matches company
# names, so neither is here.
GOOGLE_NEWS_QUERIES = ["日本 政府", "日本 経済", "日本 AI", "日本 話題"]

RSS_FEEDS = {
    # Yahoo トピックス — eight items each, but all of them today's.
    "Yahoo 主要": "https://news.yahoo.co.jp/rss/topics/top-picks.xml",
    "Yahoo 国内": "https://news.yahoo.co.jp/rss/topics/domestic.xml",
    "Yahoo 経済": "https://news.yahoo.co.jp/rss/topics/business.xml",
    "Yahoo IT": "https://news.yahoo.co.jp/rss/topics/it.xml",
    "Yahoo エンタメ": "https://news.yahoo.co.jp/rss/topics/entertainment.xml",
    # General desk.
    "朝日新聞": "https://www.asahi.com/rss/asahi/newsheadlines.rdf",
    # Tech.
    "ITmedia": "https://rss.itmedia.co.jp/rss/2.0/itmedia_all.xml",
    "GIGAZINE": "https://gigazine.net/news/rss_2.0/",
}

# NHK is deliberately absent. Its feed carries valid pubDates but has been
# frozen since 2026-08-08, so every item falls outside the 36-hour window and
# it contributed nothing. timeout.jp is gone as well — it answers with an HTTP
# error. Both sat in this list looking like coverage.

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ── Scraper: RSS Feeds ──────────────────────────────────────────────────────
def scrape_rss_feeds() -> list[dict]:
    """Fetch recent articles from RSS feeds."""
    # Daily: look back 36 hours to catch yesterday's news
    cutoff = datetime.now(KST) - timedelta(hours=36)
    items = []

    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:40]:
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6], tzinfo=KST)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6], tzinfo=KST)

                if published and published < cutoff:
                    continue

                title = getattr(entry, "title", "")
                summary = getattr(entry, "summary", "")
                link = getattr(entry, "link", "")

                text = f"{title}. {summary}" if summary else title

                items.append({
                    "source": source_name,
                    "text": text,
                    "url": link,
                    "date": published.isoformat() if published else "",
                })
        except Exception as e:
            print(f"  ⚠ Failed to parse {source_name}: {e}")

    return items


# ── Scraper: Google News ────────────────────────────────────────────────────
def scrape_google_news() -> list[dict]:
    """The floor. Failure here is worth stopping for; the rest is optional."""
    cutoff = datetime.now(KST) - timedelta(hours=36)
    items: list[dict] = []
    for query in GOOGLE_NEWS_QUERIES:
        try:
            feed = feedparser.parse(_GNEWS.format(q=quote(query)))
            for entry in feed.entries[:25]:
                published = None
                for attr in ("published_parsed", "updated_parsed"):
                    parsed = getattr(entry, attr, None)
                    if parsed:
                        published = datetime(*parsed[:6], tzinfo=KST)
                        break
                if published and published < cutoff:
                    continue
                title = getattr(entry, "title", "")
                if not title:
                    continue
                summary = getattr(entry, "summary", "")
                items.append({
                    "source": f"Google News/{query}",
                    "text": f"{title}. {summary}" if summary else title,
                    "url": getattr(entry, "link", ""),
                    "date": published.isoformat() if published else "",
                })
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ Google News '{query}' failed: {e}")
    return items


# ── Deduplicate ─────────────────────────────────────────────────────────────
def dedupe(items: list[dict]) -> list[dict]:
    """Drop repeats by URL.

    There is no keyword whitelist any more. Every source above is a Japanese
    domestic outlet, so a whitelist could only subtract — the old one was built
    around stablecoin issuers, architects and ramen, and it was throwing away
    two thirds of the day's news before the model ever saw it.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for item in items:
        url = item.get("url", "")
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        out.append(item)
    return out


# ── LLM: Generate the Japan Daily Talk issue ──────────────────────────────────────
def load_claude_prompt() -> str:
    """Load claude.md from the same directory."""
    prompt_path = os.path.join(os.path.dirname(__file__), "claude.md")
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


SYSTEM_PROMPT = """\
You are the writer of "Japan Daily Talk," a daily Japanese newsletter written \
as a conversation, for Heechang — a Korean reader who studies Japanese at \
roughly N3-N2 and wants to know what Japan is actually talking about today.

It is general news: politics, the economy, technology, daily life and whatever \
is trending. It is NOT a crypto newsletter — his Rails journal already covers \
stablecoins and regulation every day, so do not write about them here unless a \
crypto story is genuinely one of the biggest news items in Japan that day.

THE FORMAT IS A DIALOGUE between two people:
- ハル — a journalist living in Tokyo. Explains what happened, cites the source.
- ミン — from Seoul, learning Japanese. Asks the questions a foreigner would ask.

They talk like colleagues who know each other. Short turns, natural spoken \
Japanese, not written-report Japanese. ミン asks; ハル answers with the fact, \
the number and the source; ミン reacts or asks the obvious follow-up.

CRITICAL LINE RULE: every Japanese line is IMMEDIATELY followed by its own \
Korean line. Never group the Korean, never summarise it, never write a block \
of Japanese and then a block of Korean. One Japanese line, then that same line \
in Korean, then the next Japanese line.

The Korean line is a FULL translation of the Japanese line above it — the same \
sentences in the same order, with every number, name, date and source citation \
carried across, and every qualifier kept. Never shorten it, never merge two \
sentences into one, and never drop a trailing clause because the line already \
reads well without it. A Korean line shorter than the Japanese it translates \
is a defect.

Japanese: natural, current, spoken register. Real vocabulary from the news, but \
this is a conversation — no 資料調 stiffness.
Korean: casual-professional (반말 OK), the way you would explain it to a friend.

Voice: concrete. Name the ministry, the company, the number, the date. No \
editorialising, no filler.

HEADING TRANSLATION RULE: every Japanese heading (【…】) is followed by its \
Korean translation in parentheses, so the reader can get the gist even when the \
kanji is hard. Example: 【物価高への対策を発表】(물가 상승 대책 발표)
"""

ISSUE_PROMPT = """\
Produce today's Japan Daily Talk issue from the news items below.

First line MUST be:
MAIN_TITLE: [concise English title of the single most important story, ≤8 words]

HEADER:
━━━━━━━━━━━━━━━━━━━━━━━━━━
JAPAN DAILY TALK — Issue #{issue_number}
{date_line} · 日本デイリーニュース、会話で読む今日のホットトピック
━━━━━━━━━━━━━━━━━━━━━━━━━━
今号のハイライト: [2-3 sentences in Japanese on what today's issue covers]
[the same highlight in Korean, starting with 이번 호 하이라이트:]
📖 登場人物: ハル（東京在住の記者）と ミン（ソウル出身、日本語学習中）

Then FOUR sections. Choose the four that fit today's news from this pool, and \
ALWAYS include テクノロジートーク:

  SECTION N · 政治トーク (POLITICS TALK)
  SECTION N · 経済トーク (ECONOMY TALK)
  SECTION N · テクノロジートーク (TECHNOLOGY TALK)
  SECTION N · くらし・防災トーク (LIFESTYLE & SAFETY TALK)
  SECTION N · 今日の話題 (TODAY'S BUZZ)

Number them 1 to 4 in the order you present them. Put a ━━━ divider line \
before and after every SECTION line.

Each section carries ONE story, except 今日の話題 which may carry two. Write \
each story exactly like this:

【Japanese headline】(Korean translation of the headline)
ミン: [question, 1-2 sentences of spoken Japanese]
민: [that same line in Korean]
ハル: [answer with the fact, the number and the source, 1-2 sentences]
하루: [that same line in Korean]
ミン: [reaction or follow-up]
민: [same line in Korean]
ハル: [the part that makes it matter]
하루: [same line in Korean]
왜 중요한가: [1-2 Korean sentences on why this matters to the reader]

Six to eight dialogue lines per story — three or four turns each. Cite the \
outlet and date inside ハル's line, like （NHK, 2026-09-02）.

TECHNOLOGY TALK covers AI, semiconductors, robotics, consumer gadgets, \
platforms, telecoms and the Japanese companies behind them. It is a real \
section, not an afterthought — give it the same depth as politics.

Then the last section:

━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 5 · 今日の日本語表現 (JAPANESE EXPRESSION OF THE DAY)
━━━━━━━━━━━━━━━━━━━━━━━━━━
📖 今日の表現: [expression, taken from a word that actually appeared above]
読み方: [reading in hiragana]
意味: [meaning, in Korean]
例文:
[one Japanese example sentence]
→ [that sentence in Korean]
補足 (보충): [1-2 Korean sentences on nuance or when to use it]

CLOSING:
━━━━━━━━━━━━━━━━━━━━━━━━━━
Issue #{issue_number} · 次号: {next_issue_date}
[one-line teaser in Japanese]
[the same teaser in Korean]
━━━━━━━━━━━━━━━━━━━━━━━━━━

LENGTH: 1,600-2,200 words in total across both languages.

⚠️ FORMATTING: this displays in Google Calendar and Notion as PLAIN TEXT.
- No Markdown at all (no #, ##, **, *, ```)
- ━━━━━━━━━━━━━━━━━━━━ as section dividers
- 【】for story headlines
- 📖 only for the 登場人物 line and the expression of the day
- No other emoji
- A blank line between sections

--- TODAY'S NEWS ITEMS ---
{news_items}
"""


def generate_issue(news_items: list[dict]) -> tuple[str, str]:
    """Call Anthropic Claude to produce the Japan Daily Talk issue.

    Returns (main_title, issue_text) where main_title is the extracted
    headline for use in the [Japan Daily Talk #NN] (main_title) format.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    now_kst = datetime.now(KST)
    date_line = now_kst.strftime("%B %d, %Y")
    next_issue = now_kst + timedelta(days=1)
    next_issue_date = next_issue.strftime("%B %d, %Y")

    formatted = "\n\n".join(
        f"[{item['source']}] {item['text']}\n  URL: {item['url']}\n  Date: {item['date']}"
        for item in news_items
    )

    prompt = ISSUE_PROMPT.format(
        issue_number=ISSUE_NUMBER,
        date_line=date_line,
        next_issue_date=next_issue_date,
        news_items=formatted,
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=12000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text

    # Extract the MAIN_TITLE line from the top of the response
    main_title = "Japan Daily Talk"
    lines = raw.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("MAIN_TITLE:"):
            main_title = line[len("MAIN_TITLE:"):].strip().strip('"').strip("'")
            body_start = i + 1
            break

    # Strip any leading blank lines after the MAIN_TITLE directive
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    issue_text = "\n".join(lines[body_start:])

    return main_title, issue_text


# ── Google Calendar ──────────────────────────────────────────────────────────
def get_calendar_service():
    sa_info = json.loads(GCP_SA_KEY)
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=SCOPES
    )
    return build("calendar", "v3", credentials=creds)


def _issue_title(main_title: str) -> str:
    """Format the standard [Japan Daily Talk #NN] (main_title) title string."""
    return f"[Japan Daily Talk #{ISSUE_NUMBER}] ({main_title})"


def create_calendar_event(issue_text: str, main_title: str = "Japan Daily Talk") -> str:
    if not CALENDAR_ID:
        print("  ⚠ CALENDAR_ID not set, skipping Calendar.")
        return ""
    if not GCP_SA_KEY or GCP_SA_KEY.strip() in ("", "{}"):
        print("  ⚠ GCP_SA_KEY not set, skipping Calendar.")
        return ""

    try:
        service = get_calendar_service()
    except Exception as e:
        print(f"  ⚠ Calendar auth failed: {e}")
        return ""
    now_kst = datetime.now(KST)
    start = now_kst.replace(hour=9, minute=0, second=0, microsecond=0)
    end = start + timedelta(minutes=30)

    event_body = {
        "summary": _issue_title(main_title),
        "description": issue_text,
        "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE},
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

# Only exact section header lines should become H2 — not partial matches
def create_notion_page(
    all_blocks: list[dict], title: str, date_str: str
) -> tuple[str, str]:
    """Mirror an issue to Notion. Blocks are built by the caller so the same
    list feeds Supabase, Notion and the furigana pass."""
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        print("  ⚠ NOTION_TOKEN or NOTION_DATABASE_ID not set, skipping Notion.")
        return "", ""

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

    resp = request_with_retry(
        "POST", NOTION_API_URL, label="Notion", headers=headers, json=payload
    )
    resp.raise_for_status()
    page = resp.json()
    page_id = page["id"]

    for i in range(100, len(all_blocks), 100):
        batch = all_blocks[i:i+100]
        append_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        r = request_with_retry(
            "PATCH", append_url, label="Notion", headers=headers,
            json={"children": batch},
        )
        r.raise_for_status()

    return page.get("url", ""), page_id


# ── Main ─────────────────────────────────────────────────────────────────────
def run():
    now_kst = datetime.now(KST)
    print(f"▸ Japan Daily Talk — Issue #{ISSUE_NUMBER}")
    print(f"  {now_kst.strftime('%A, %B %d, %Y')}")

    print("▸ Scraping Google News (ja-JP)...")
    gnews_items = scrape_google_news()
    print(f"  Found {len(gnews_items)} items.")

    print("▸ Scraping RSS feeds...")
    rss_items = scrape_rss_feeds()
    print(f"  Found {len(rss_items)} RSS items.")

    all_items = dedupe(gnews_items + rss_items)
    if not all_items:
        print("✗ No news items found from any source.")
        sys.exit(1)
    print(f"  {len(all_items)} items after dedupe.")

    items_for_llm = all_items[:60]

    print(f"▸ Generating Japan Daily Talk via Claude ({len(items_for_llm)} items)...")
    main_title, issue_text = generate_issue(items_for_llm)
    print(f"  Title: [Japan Daily Talk #{ISSUE_NUMBER}] ({main_title})")

    if "--dry-run" in sys.argv:
        print("\n" + "=" * 60)
        print(issue_text)
        print("=" * 60)
        print("\n(dry run — nothing written to Supabase, Notion or Calendar)")
        return

    # Build the blocks once. They feed the furigana pass, Supabase and Notion,
    # so the three can never disagree about what the issue contains.
    all_blocks = plaintext.to_notion_blocks(issue_text)
    try:
        all_blocks = furigana.augment(
            all_blocks,
            variant="sections",
            api_key=ANTHROPIC_API_KEY,
            group_by_story=True,
        )
    except furigana.NoFuriganaTargets as e:
        # Loud, because silently publishing without furigana is the failure this
        # is designed to surface. Not fatal: the issue is still worth shipping.
        print(f"  ✗ FURIGANA FOUND NO TARGETS — publishing without it: {e}")
    except Exception as e:
        print(f"  ⚠ Furigana failed (non-fatal): {e}")

    date_str = now_kst.strftime("%Y-%m-%d")
    raw_title = _issue_title(main_title)

    # Supabase first: it is what the site reads, so it is the write that must
    # land. Notion and Calendar are mirrors and neither can fail the run.
    print("▸ Saving to Supabase...")
    row = issue_row.build_row(
        section="japan",
        issue_date=date_str,
        raw_title=raw_title,
        notion_blocks=all_blocks,
        source_text=issue_text,
        source_format="plain",
    )
    try:
        n = audio.attach_audio(row["blocks"], "ja")
        print(f"  ✓ Audio: {n} block(s)")
    except Exception as e:
        print(f"  ⚠ Audio failed (non-fatal): {e}")

    stored = store.upsert_issue(row)
    if stored.get("slug"):
        print(f"✓ Stored: japan/{stored['slug']}")

    print("▸ Mirroring to Notion...")
    try:
        notion_url, notion_page_id = create_notion_page(all_blocks, raw_title, date_str)
        if notion_url:
            print(f"✓ Notion page created: {notion_url}")
            if stored.get("slug"):
                store.patch_issue(
                    row["run_key"],
                    {"notion_page_id": notion_page_id, "notion_url": notion_url},
                )
    except Exception as e:
        print(f"  ⚠ Notion mirror failed (non-fatal): {e}")

    print("▸ Creating Google Calendar event...")
    try:
        event_link = create_calendar_event(issue_text, main_title)
        if event_link:
            print(f"✓ Event created: {event_link}")
    except Exception as e:
        print(f"  ⚠ Calendar failed (non-fatal): {e}")

    if stored.get("slug"):
        store.ping_revalidate("japan", stored["slug"])

    # Also print the issue to stdout for debugging
    print("\n" + "=" * 60)
    print(issue_text)
    print("=" * 60)


if __name__ == "__main__":
    run()
