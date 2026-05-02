#!/usr/bin/env python3
"""Rails — Daily Financial Infrastructure Newsletter → Google Calendar.

Scrapes financial infra / stablecoin / RWA / crypto regulation news from
multiple sources, generates a "Rails" issue via Anthropic Claude following
the format spec in claude.md, and inserts a calendar event at 09:00 KST.
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
GCP_SA_KEY = os.environ["GCP_SA_KEY"]  # JSON string of service account key
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.environ.get(
    "NOTION_DATABASE_ID",
    "3535bc953df3807b83c9dc5be40b72e6",
)
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Seoul")
SCOPES = ["https://www.googleapis.com/auth/calendar"]
KST = timezone(timedelta(hours=9))

# Issue counter file (persisted via git or env)
ISSUE_NUMBER = int(os.environ.get("ISSUE_NUMBER", "1"))

# ── News Sources ────────────────────────────────────────────────────────────
RSS_FEEDS = {
    # Crypto / digital assets
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "The Block": "https://www.theblock.co/rss.xml",
    "DL News": "https://www.dlnews.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
    # Fintech / payments / tradfi
    "PYMNTS": "https://www.pymnts.com/feed/",
    "Finextra": "https://www.finextra.com/rss/headlines.aspx",
    "American Banker": "https://www.americanbanker.com/feed",
    "Tearsheet": "https://tearsheet.co/feed/",
    "Fintech Futures": "https://www.fintechfutures.com/feed/",
    # Asia finance
    "Nikkei Asia": "https://asia.nikkei.com/rss",
}

TELEGRAM_CHANNELS = [
    "https://t.me/s/TheBlock__",
    "https://t.me/s/CoinDesk",
]

# Keywords to filter for financial infra relevance
INFRA_KEYWORDS = [
    # Stablecoins & digital assets
    "stablecoin", "USDC", "USDT", "Tether", "Circle", "PYUSD",
    "RWA", "tokeniz", "real world asset", "real-world asset",
    "custody", "custodian", "settlement", "clearing",
    "CBDC", "digital currency",
    # Payments & fintech
    "payment rail", "cross-border", "remittance",
    "real-time payment", "instant payment", "FedNow", "UPI", "Pix",
    "open banking", "embedded finance", "BaaS", "banking-as-a-service",
    "neobank", "digital bank", "challenger bank",
    "card network", "interchange", "acquiring", "issuing",
    "money transfer", "forex", "FX", "treasury management",
    "paytech", "fintech", "regtech", "wealthtech",
    "Stripe", "Adyen", "Wise", "Plaid", "Marqeta", "Checkout.com",
    # Regulators & policy
    "Korea", "Japan", "Hong Kong", "Singapore", "FSC", "BOK", "FSA",
    "MAS", "HKMA", "SEC", "CFTC", "OCC", "FDIC", "Fed ",
    "regulation", "regulatory", "compliance", "license",
    "Basel", "capital requirement", "AML", "KYC",
    # Institutions & tradfi
    "institutional", "bank", "BlackRock", "Fidelity", "JPMorgan",
    "Goldman", "Morgan Stanley", "Citi", "BNY", "State Street",
    "Visa", "Mastercard", "Swift", "SWIFT", "DTCC",
    "issuance", "distribution", "infrastructure", "infra",
    # Crypto infra
    "Pantera", "staking", "yield", "treasury",
    "Layer", "bridge", "interop", "LayerZero",
    "Hyperliquid", "Ondo", "Securitize", "Hashnote",
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
    cutoff = datetime.now(KST) - timedelta(hours=36)
    items = []

    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:30]:  # last 30 entries per feed
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6], tzinfo=KST)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6], tzinfo=KST)

                # Skip old articles
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
def filter_infra_relevant(items: list[dict]) -> list[dict]:
    """Keep items matching financial infrastructure keywords."""
    keywords_lower = [k.lower() for k in INFRA_KEYWORDS]
    filtered = []
    seen_urls = set()

    for item in items:
        text_lower = item["text"].lower()
        url = item.get("url", "")

        # Deduplicate by URL
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        # Keyword match
        if any(kw in text_lower for kw in keywords_lower):
            filtered.append(item)

    return filtered


# ── LLM: Generate Rails Issue ───────────────────────────────────────────────
WEEKDAY_ROTATION = {
    0: "Thesis Monday",
    1: "Counter-Take Tuesday",
    2: "Data Point Wednesday",
    3: "Throwback Thursday",
    4: "Founder Friday",
    5: "Long Read Saturday",
    6: "Week in Review Sunday",
}

TOMORROW_ROTATION = {
    0: "Counter-Take Tuesday",
    1: "Data Point Wednesday",
    2: "Throwback Thursday",
    3: "Founder Friday",
    4: "Long Read Saturday",
    5: "Week in Review Sunday",
    6: "Thesis Monday",
}

SYSTEM_PROMPT = """\
You are the writer of "Rails," a daily journal on the future of financial \
infrastructure written for Heechang — co-founder/CSO at Four Pillars, \
Seoul-based institutional crypto research firm backed by Pantera/Kakao \
Ventures/Hashed.

Active research streams: Asia stablecoin corridors, KRW stablecoin \
legislation (DABA), Hong Kong/Japan stablecoin infra, RWA institutional \
adoption, custody.

Active org initiatives: ASA (Asia Stablecoin Alliance) with LayerZero, \
HRC (Hyperliquid Research Collective), FPAP (advisory), FP Validated.

Active deliverable: Pantera x Four Pillars joint institutional report.

Editorial priors (color your takes, but push back when evidence warrants):
- Stablecoins win first as plumbing for incumbents, not as challengers
- The Asia corridor (KR-JP-HK-SG) is undercovered relative to its real volume
- Institutional adoption follows infrastructure maturity, not regulatory clarity
- Bank-led stablecoin frameworks are last-decade answers to next-decade questions
- Custody is the unsolved bottleneck, not issuance

Voice: tight, not academic. Short sentences. Active voice. Have a take. \
No hedge language. No corporate-speak. No emoji. English only.\
"""

ISSUE_PROMPT = """\
Produce a complete Rails issue from the news items below. Follow this \
structure exactly:

HEADER:
# Rails — Issue #{issue_number}
{date_line} · Heechang's daily journal on the future of financial infrastructure

SECTION 1 — THREE DEEP READS:
Pick the 3 most consequential stories for financial infrastructure from the \
last 24 hours. Bias toward: stablecoins, RWA & tokenization, custody & \
settlement infra, Asia regulatory developments, institutional adoption, \
payment rails. De-prioritize token price action, retail narratives, NFT/meme.

For EACH of the three:
N. [Headline as single declarative sentence]

What happened. 2-3 sentences, cite sources.
What it means. Non-obvious read, not consensus. 4-6 sentences.
Infra implication. Which layer (issuance/settlement/custody/distribution/compliance), \
accelerate or delay trajectory. Tie to ongoing work. 2-4 sentences.
Open question. One sentence.

SECTION 2 — THE SWEEP:
8-12 headlines, one line each, grouped by region:
Americas / Asia / Europe / Infra & markets
Skip a group if nothing meaningful. Don't pad.

SECTION 3 — FOOD FOR THOUGHT:
Today is {weekday}. Today's rotation: {rotation_slot}.
{rotation_instructions}

CLOSING:
Single italicized line: issue number, estimated minutes elapsed, \
one-line teaser for tomorrow's rotation ({tomorrow_slot}).

LENGTH: 900-1,300 words total. If pushing past 1,400, cut.

If signal is thin, say so. Don't manufacture three Deep Reads when only \
two stories warrant it.

⚠️ FORMATTING: This will display inside a Google Calendar event (PLAIN TEXT).
- Do NOT use Markdown (no #, ##, **, *, ```, etc.)
- Use ━━━━━━━━━━━━━━━━━━━━ as section dividers
- Use ALL CAPS for section headers
- Use ▸ for bullet points
- Use blank lines between sections
- No emoji except in the closing line

--- TODAY'S NEWS ITEMS ---
{news_items}
"""

ROTATION_INSTRUCTIONS = {
    0: "Thesis Monday: State or sharpen a current conviction. Bold the thesis as the first line, then 4-6 sentences arguing it.",
    1: "Counter-Take Tuesday: Steelman a position Heechang would disagree with. Not a strawman. 5-7 sentences.",
    2: "Data Point Wednesday: One number or chart-worthy stat + why it matters. Lead with the number in bold. 3-5 sentences.",
    3: "Throwback Thursday: A piece of financial history that rhymes with today (Eurodollar markets, Bretton Woods, MMF reform, etc.). Name the event, draw the parallel, name the lesson. 5-8 sentences.",
    4: "Founder Friday: A question you'd ask a founder building in the space. Lead with the question in italics, then 2-3 sentences of framing.",
    5: "Long Read Saturday: A quote from a paper, book, or essay (15 words max, paraphrase the rest) + reaction. 5-8 sentences.",
    6: "Week in Review Sunday: Pull the thread across the week. What story compounded? What question resolved? 6-10 sentences.",
}


def generate_issue(news_items: list[dict]) -> str:
    """Call Anthropic Claude to produce the Rails issue."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    now_kst = datetime.now(KST)
    weekday = now_kst.weekday()
    date_line = now_kst.strftime("%A, %B %d, %Y")
    today_str = now_kst.strftime("%B %d, %Y")

    formatted = "\n\n".join(
        f"[{item['source']}] {item['text']}\n  URL: {item['url']}\n  Date: {item['date']}"
        for item in news_items
    )

    prompt = ISSUE_PROMPT.format(
        issue_number=ISSUE_NUMBER,
        date_line=date_line,
        weekday=now_kst.strftime("%A"),
        rotation_slot=WEEKDAY_ROTATION[weekday],
        rotation_instructions=ROTATION_INSTRUCTIONS[weekday],
        tomorrow_slot=TOMORROW_ROTATION[weekday],
        news_items=formatted,
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
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


def create_calendar_event(issue_text: str) -> str:
    """Insert a 30-min event at 09:00 KST with the issue as description."""
    service = get_calendar_service()

    now_kst = datetime.now(KST)
    start = now_kst.replace(hour=9, minute=0, second=0, microsecond=0)
    end = start + timedelta(minutes=30)

    event_body = {
        "summary": f"Rails — Issue #{ISSUE_NUMBER} · {now_kst.strftime('%b %d, %Y')}",
        "description": issue_text,
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


# Section headers to detect (ALL CAPS lines from the newsletter)
_SECTION_HEADERS = [
    "THREE DEEP READS", "THE SWEEP", "FOOD FOR THOUGHT",
    "AMERICAS", "ASIA", "EUROPE", "INFRA & MARKETS",
    "THESIS MONDAY", "COUNTER-TAKE TUESDAY", "DATA POINT WEDNESDAY",
    "THROWBACK THURSDAY", "FOUNDER FRIDAY", "LONG READ SATURDAY",
    "WEEK IN REVIEW SUNDAY", "OTHER NOTABLE", "CLOSING",
]


def _rich_text(content: str, bold: bool = False, italic: bool = False,
               color: str = "default") -> dict:
    """Build a single Notion rich-text object."""
    rt = {
        "type": "text",
        "text": {"content": content[:2000]},
        "annotations": {
            "bold": bold,
            "italic": italic,
            "strikethrough": False,
            "underline": False,
            "code": False,
            "color": color,
        },
    }
    return rt


def _is_section_header(line: str) -> bool:
    """Check if a line is an ALL-CAPS section header."""
    stripped = line.strip()
    if not stripped:
        return False
    return any(h in stripped.upper() for h in _SECTION_HEADERS)


def _is_divider(line: str) -> bool:
    """Check if a line is a section divider (━━━)."""
    return "━" in line and line.strip().count("━") >= 5


def _text_to_notion_blocks(text: str) -> list[dict]:
    """Convert the Rails newsletter plain text into formatted Notion blocks."""
    blocks = []
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            i += 1
            continue

        # ── Divider lines (━━━) ──
        if _is_divider(stripped):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue

        # ── Title line (Rails — Issue #...) ──
        if stripped.startswith("Rails") and "Issue" in stripped:
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [_rich_text(stripped, bold=True)],
                    "color": "purple_background",
                    "is_toggleable": False,
                },
            })
            i += 1
            continue

        # ── Section headers (ALL CAPS) ──
        if _is_section_header(stripped):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [_rich_text(stripped, bold=True)],
                    "color": "purple_background",
                    "is_toggleable": False,
                },
            })
            i += 1
            continue

        # ── Numbered deep-read headlines (1. 2. 3.) ──
        if len(stripped) > 2 and stripped[0].isdigit() and stripped[1] == ".":
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [_rich_text(stripped, bold=True)],
                    "color": "default",
                    "is_toggleable": False,
                },
            })
            i += 1
            continue

        # ── Bullet points (▸) ──
        if stripped.startswith("▸"):
            bullet_text = stripped[1:].strip()
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [_rich_text(bullet_text)],
                },
            })
            i += 1
            continue

        # ── Sub-labels (What happened, What it means, etc.) ──
        lower = stripped.lower()
        if any(lower.startswith(label) for label in [
            "what happened", "what it means", "infra implication", "open question",
        ]):
            # Split at the first period-space to bold the label
            if ". " in stripped:
                label_part, rest = stripped.split(". ", 1)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            _rich_text(label_part + ". ", bold=True, color="purple"),
                            _rich_text(rest),
                        ],
                    },
                })
            else:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [_rich_text(stripped, bold=True, color="purple")],
                    },
                })
            i += 1
            continue

        # ── Closing / italic line ──
        if i >= len(lines) - 3 and ("issue" in lower or "minute" in lower):
            blocks.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [_rich_text(stripped, italic=True)],
                    "icon": {"type": "emoji", "emoji": "🚂"},
                    "color": "purple_background",
                },
            })
            i += 1
            continue

        # ── Date / subtitle line (right after title) ──
        if i <= 3 and ("journal" in lower or "daily" in lower):
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [_rich_text(stripped, italic=True, color="gray")],
                },
            })
            i += 1
            continue

        # ── Default: regular paragraph ──
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [_rich_text(stripped)],
            },
        })
        i += 1

    return blocks


def create_notion_page(issue_text: str) -> str:
    """Create a Notion page in the newsletter database with the issue content."""
    if not NOTION_TOKEN:
        print("  ⚠ NOTION_TOKEN not set, skipping Notion.")
        return ""

    now_kst = datetime.now(KST)
    title = f"Rails — Issue #{ISSUE_NUMBER} · {now_kst.strftime('%b %d, %Y')}"

    # Notion API limits children to 100 blocks per request
    all_blocks = _text_to_notion_blocks(issue_text)

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
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
        batch = all_blocks[i:i+100]
        append_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        r = requests.patch(append_url, headers=headers, json={"children": batch}, timeout=30)
        r.raise_for_status()

    return page.get("url", "")


# ── Main ─────────────────────────────────────────────────────────────────────
def run():
    now_kst = datetime.now(KST)
    print(f"▸ Rails — Issue #{ISSUE_NUMBER}")
    print(f"  {now_kst.strftime('%A, %B %d, %Y')} ({WEEKDAY_ROTATION[now_kst.weekday()]})")

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

    print("▸ Filtering for financial infra relevance...")
    filtered = filter_infra_relevant(all_items)
    print(f"  {len(filtered)} relevant items (from {len(all_items)} total).")

    # If filtering is too aggressive, fall back to all items
    items_for_llm = filtered if len(filtered) >= 5 else all_items
    # Cap at 50 items to stay within token limits
    items_for_llm = items_for_llm[:50]

    print(f"▸ Generating Rails issue via Claude ({len(items_for_llm)} items)...")
    issue_text = generate_issue(items_for_llm)

    print("▸ Creating Google Calendar event...")
    event_link = create_calendar_event(issue_text)
    print(f"✓ Event created: {event_link}")

    print("▸ Saving to Notion...")
    notion_url = create_notion_page(issue_text)
    if notion_url:
        print(f"✓ Notion page created: {notion_url}")


if __name__ == "__main__":
    run()
