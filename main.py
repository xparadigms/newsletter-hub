#!/usr/bin/env python3
"""Japan Briefing — Bi-weekly bilingual newsletter → Google Calendar + Notion.

Scrapes Japan crypto/regulation/real-estate news from Japanese and English
sources, generates a bilingual (JP body + KR translation) issue via Claude,
and inserts a calendar event + Notion page.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import anthropic
import feedparser
import requests
from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build

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

# ── News Sources (Japan-focused) ────────────────────────────────────────────
RSS_FEEDS = {
    # Japanese crypto / regulation
    "CoinPost": "https://coinpost.jp/?feed=rss2",
    "CoinDesk Japan": "https://www.coindeskjapan.com/feed/",
    # English crypto (Japan-relevant stories)
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "The Block": "https://www.theblock.co/rss.xml",
    "DL News": "https://www.dlnews.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
    # Japanese general / finance / real estate
    "NHK News": "https://www3.nhk.or.jp/rss/news/cat0.xml",
    "ITmedia": "https://rss.itmedia.co.jp/rss/2.0/itmedia_all.xml",
    # Asia finance
    "Nikkei Asia": "https://asia.nikkei.com/rss",
}

TELEGRAM_CHANNELS = [
    "https://t.me/s/TheBlock__",
    "https://t.me/s/CoinDesk",
]

# Keywords to filter for Japan crypto/regulation/real-estate relevance
JAPAN_KEYWORDS = [
    # Japan-specific
    "Japan", "Japanese", "日本", "東京", "Tokyo",
    "FSA", "金融庁", "JVCEA", "FIEA", "金商法", "資金決済法",
    "stablecoin", "ステーブルコイン", "JPYC", "Progmat", "Project Pax",
    "MUFG", "三菱UFJ", "SMBC", "三井住友", "Mizuho", "みずほ",
    "SBI", "Startale", "Strium", "Metaplanet",
    "bitFlyer", "Coincheck", "bitbank", "GMO", "Rakuten",
    "Nomura", "野村", "Daiwa", "大和",
    # Crypto infra (Japan-relevant)
    "USDC", "Circle", "stablecoin", "tokeniz", "RWA",
    "custody", "settlement", "CBDC", "digital yen", "デジタル円",
    "insider trading", "disclosure", "regulation", "regulatory",
    # Real estate / urban development
    "再開発", "redevelopment", "不動産", "real estate",
    "容積率", "FAR", "都市計画", "urban planning",
    "マンション", "タワー", "tower", "ヒルズ", "Hills",
    "渋谷", "Shibuya", "六本木", "Roppongi", "麻布", "Azabudai",
    "虎ノ門", "Toranomon", "品川", "Shinagawa",
    # Korea-Japan cross-border
    "Korea", "韓国", "KRW", "won",
    "Asia", "アジア", "Hong Kong", "Singapore",
]

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


# ── Scraper: Telegram ───────────────────────────────────────────────────────
def scrape_telegram_channels() -> list[dict]:
    """Fetch latest posts from Telegram public channels."""
    items = []
    for channel_url in TELEGRAM_CHANNELS:
        try:
            resp = requests.get(channel_url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            for widget in soup.select("div.tgme_widget_message_wrap"):
                text_el = widget.select_one("div.tgme_widget_message_text")
                if not text_el:
                    continue

                text = text_el.get_text(separator=" ", strip=True)
                link_el = text_el.select_one("a[href]")
                url = link_el["href"] if link_el else ""
                date_el = widget.select_one("time[datetime]")
                date_str = date_el["datetime"] if date_el else ""

                if text:
                    source = channel_url.split("/s/")[-1] if "/s/" in channel_url else "Telegram"
                    items.append({
                        "source": f"Telegram/{source}",
                        "text": text,
                        "url": url,
                        "date": date_str,
                    })
        except Exception as e:
            print(f"  ⚠ Failed to scrape {channel_url}: {e}")

    return items


# ── Filter & Deduplicate ────────────────────────────────────────────────────
def filter_japan_relevant(items: list[dict]) -> list[dict]:
    """Keep items matching Japan crypto/regulation/real-estate keywords."""
    keywords_lower = [k.lower() for k in JAPAN_KEYWORDS]
    filtered = []
    seen_urls = set()

    for item in items:
        text_lower = item["text"].lower()
        url = item.get("url", "")

        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        if any(kw in text_lower for kw in keywords_lower):
            filtered.append(item)

    return filtered


# ── LLM: Generate Japan Briefing Issue ──────────────────────────────────────
def load_claude_prompt() -> str:
    """Load claude.md from the same directory."""
    prompt_path = os.path.join(os.path.dirname(__file__), "claude.md")
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


SYSTEM_PROMPT = """\
You are the writer of "Japan Briefing," a bi-weekly bilingual newsletter on \
Japan's crypto regulation, stablecoin infrastructure, and urban development, \
written for Heechang — co-founder/CSO at Four Pillars, Seoul-based \
institutional crypto research firm backed by Pantera/Kakao Ventures/Hashed.

CRITICAL FORMAT RULE: Every substantive section must be written FIRST in \
Japanese (日本語), then immediately followed by a COMPLETE Korean translation \
(한국어 번역) marked with 📝. The Korean translation must translate EVERY \
sentence from the Japanese — do NOT summarize, do NOT omit, do NOT \
paraphrase into a shorter version. Translate the full Japanese text \
sentence-by-sentence into Korean, then add the "왜 중요한가" line.

Japanese: natural, native-level business Japanese. Use real industry \
terminology (資金決済法, 金商法, ステーブルコイン, 再開発).
Korean: casual-professional (반말 OK). Like explaining to a colleague. \
But translate EVERYTHING — no omissions.

Active research: Asia stablecoin corridors, KRW stablecoin legislation, \
Japan stablecoin infra (JPYC, Progmat, megabank pilots), FIEA analysis.
Active orgs: ASA (Asia Stablecoin Alliance), HRC, FPAP, FP Validated.

Editorial priors:
- Japan's FIEA reclassification is the most consequential crypto event in Asia
- The KR-JP stablecoin corridor is undercovered
- Megabank stablecoin frameworks are slow but have unmatched distribution
- Tokyo's private-led redevelopment is 10 years ahead of Seoul

Voice: tight, analytical, bilingual. Have a take. No filler.

PARAGRAPH RULE: Keep every paragraph to 3 sentences MAX. If a block of \
text would be 4+ sentences, break it into multiple paragraphs with a \
blank line between them. This applies to BOTH Japanese and Korean sections. \
Short paragraphs are easier to read on mobile and in Notion.

HEADING TRANSLATION RULE: All Japanese headings (【見出し】, section titles, \
etc.) must also include a Korean translation in parentheses right after. \
Example: 【改正資金決済法の政令が公布】(개정 자금결제법 정령 공포) \
This way the reader can understand the headline even if the kanji is hard.\
"""

ISSUE_PROMPT = """\
Produce a complete Japan Briefing issue from the news items below.

HEADER:
━━━━━━━━━━━━━━━━━━━━━━━━━━
JAPAN BRIEFING — Issue #{issue_number}
{date_line} · 日本クリプト・不動産ブリーフィング
━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION 1 — 日本クリプト・規制ウォッチ (JAPAN CRYPTO & REGULATION WATCH):
Pick 2-3 most consequential Japan crypto/stablecoin/regulation stories.
For EACH story:
【見出し】 Headline in Japanese
Japanese body (3-4 sentences, cite sources, use real terminology)
📝 한국어 번역:
Full Korean translation of EVERY sentence above (do NOT summarize or shorten).
Then add: 왜 중요한가: [1-2 sentences connecting to ASA/ASC/FP work]

SECTION 2 — 不動産・都市開発 (REAL ESTATE & URBAN DEVELOPMENT):
1-2 stories on Tokyo/Japan urban development. Same bilingual format.
"Seoul's 10 years from now" angle.

SECTION 3 — 今週の日本語表現 (JAPANESE EXPRESSION OF THE WEEK):
📖 今週の表現: [expression]
読み方: [reading]
意味: [Korean meaning]
例文: [Japanese example]
→ [Korean translation]

SECTION 4 — カルチャー・ひとくち (CULTURE BITE):
One light item, JP + KR. 3-4 sentences.

CLOSING:
━━━━━━━━━━━━━━━━━━━━━━━━━━
Issue #{issue_number} · 次号: {next_issue_date}
[One-line teaser JP + KR]
━━━━━━━━━━━━━━━━━━━━━━━━━━

LENGTH: 1,200-1,800 words total.

PARAGRAPH RULE: Every paragraph must be 3 sentences or fewer. \
If a thought needs 4+ sentences, split into separate paragraphs \
with a blank line. This applies to both JP and KR sections.

⚠️ FORMATTING: Display in Calendar/Notion (PLAIN TEXT).
- No Markdown
- Use ━━━ as section dividers
- ALL CAPS for English section headers
- 【】for Japanese sub-headers
- 📝 for Korean translations
- 📖 for expression section

--- NEWS ITEMS FROM LAST 2 WEEKS ---
{news_items}
"""


def generate_issue(news_items: list[dict]) -> str:
    """Call Anthropic Claude to produce the Japan Briefing issue."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    now_kst = datetime.now(KST)
    date_line = now_kst.strftime("%B %d, %Y")
    next_issue = now_kst + timedelta(days=14)
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
        max_tokens=6000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# ── Google Calendar ──────────────────────────────────────────────────────────
def get_calendar_service():
    sa_info = json.loads(GCP_SA_KEY)
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=SCOPES
    )
    return build("calendar", "v3", credentials=creds)


def create_calendar_event(issue_text: str) -> str:
    if not CALENDAR_ID:
        print("  ⚠ CALENDAR_ID not set, skipping Calendar.")
        return ""
    if not GCP_SA_KEY:
        print("  ⚠ GCP_SA_KEY not set, skipping Calendar.")
        return ""

    service = get_calendar_service()
    now_kst = datetime.now(KST)
    start = now_kst.replace(hour=9, minute=0, second=0, microsecond=0)
    end = start + timedelta(minutes=30)

    event_body = {
        "summary": f"Japan Briefing — Issue #{ISSUE_NUMBER} · {now_kst.strftime('%b %d, %Y')}",
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
_SECTION_HEADER_EXACT = [
    "SECTION 1",
    "SECTION 2",
    "SECTION 3",
    "SECTION 4",
    "JAPAN CRYPTO & REGULATION WATCH",
    "REAL ESTATE & URBAN DEVELOPMENT",
    "JAPANESE EXPRESSION OF THE WEEK",
    "CULTURE BITE",
]


def _rich_text(content: str) -> dict:
    return {"type": "text", "text": {"content": content[:2000]}}


def _is_section_header(line: str) -> bool:
    """Only match lines that ARE section headers, not body text containing those words."""
    stripped = line.strip()
    if not stripped:
        return False
    # Must start with SECTION or be a standalone header line (short, ALL CAPS or JP header)
    upper = stripped.upper()
    if upper.startswith("SECTION "):
        return True
    # Match exact standalone header lines only (not body text that happens to contain keywords)
    return any(upper == h or stripped == h for h in _SECTION_HEADER_EXACT)


def _is_divider(line: str) -> bool:
    return "━" in line and line.strip().count("━") >= 5


def _text_to_notion_blocks(text: str) -> list[dict]:
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
                "heading_2": {"rich_text": [_rich_text(stripped)], "is_toggleable": False},
            })
            continue
        # Only 【見出し】 lines that are actual story headlines should be H3
        # They must start with 【 and be short enough to be a headline (< 80 chars)
        if stripped.startswith("【") and "】" in stripped and len(stripped) < 120:
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [_rich_text(stripped)], "is_toggleable": False},
            })
            continue
        # 📝 and 📖 markers — only the marker line itself is a callout header,
        # the body text below should be regular paragraphs
        if stripped in ("📝 한국어 번역:", "📝 한국어 번역", "📝 한국어번역:", "📝 한국어번역"):
            blocks.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [_rich_text("한국어 번역")],
                    "icon": {"emoji": "📝"},
                },
            })
            continue
        if stripped.startswith("📖"):
            blocks.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [_rich_text(stripped[1:].strip())],
                    "icon": {"emoji": "📖"},
                },
            })
            continue
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [_rich_text(stripped)]},
        })
    return blocks


def create_notion_page(issue_text: str) -> str:
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        print("  ⚠ NOTION_TOKEN or NOTION_DATABASE_ID not set, skipping Notion.")
        return ""

    now_kst = datetime.now(KST)
    title = f"Japan Briefing — Issue #{ISSUE_NUMBER} · {now_kst.strftime('%b %d, %Y')}"
    all_blocks = _text_to_notion_blocks(issue_text)
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

    for i in range(100, len(all_blocks), 100):
        batch = all_blocks[i:i+100]
        append_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        r = requests.patch(append_url, headers=headers, json={"children": batch}, timeout=30)
        r.raise_for_status()

    return page.get("url", "")


# ── Main ─────────────────────────────────────────────────────────────────────
def run():
    now_kst = datetime.now(KST)
    print(f"▸ Japan Briefing — Issue #{ISSUE_NUMBER}")
    print(f"  {now_kst.strftime('%A, %B %d, %Y')}")

    print("▸ Scraping RSS feeds...")
    rss_items = scrape_rss_feeds()
    print(f"  Found {len(rss_items)} RSS items.")

    print("▸ Scraping Telegram channels...")
    tg_items = scrape_telegram_channels()
    print(f"  Found {len(tg_items)} Telegram items.")

    all_items = rss_items + tg_items
    if not all_items:
        print("✗ No news items found from any source.")
        sys.exit(1)

    print("▸ Filtering for Japan relevance...")
    filtered = filter_japan_relevant(all_items)
    print(f"  {len(filtered)} relevant items (from {len(all_items)} total).")

    items_for_llm = filtered if len(filtered) >= 5 else all_items
    items_for_llm = items_for_llm[:50]

    print(f"▸ Generating Japan Briefing via Claude ({len(items_for_llm)} items)...")
    issue_text = generate_issue(items_for_llm)

    print("▸ Creating Google Calendar event...")
    event_link = create_calendar_event(issue_text)
    if event_link:
        print(f"✓ Event created: {event_link}")

    print("▸ Saving to Notion...")
    notion_url = create_notion_page(issue_text)
    if notion_url:
        print(f"✓ Notion page created: {notion_url}")

    # Also print the issue to stdout for debugging
    print("\n" + "=" * 60)
    print(issue_text)
    print("=" * 60)


if __name__ == "__main__":
    run()
