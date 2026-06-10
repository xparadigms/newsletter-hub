#!/usr/bin/env python3
"""Rails — Daily Financial Infrastructure Newsletter → Google Calendar.

Scrapes financial infra / stablecoin / RWA / crypto regulation news from
multiple sources, generates a "Rails" issue via Anthropic Claude following
the format spec in claude.md, and inserts a calendar event at 09:00 KST.
"""

import json
import os
import sys
import time
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
No hedge language. No corporate-speak. No emoji.

TRILINGUAL FORMAT — this is non-negotiable:
- Every substantive section is written FIRST in English, then immediately \
followed by a Japanese translation (🇯🇵 日本語), then a Korean translation (📝 한국어 번역).
- English: your default voice — sharp, analytical, institutional.
- Japanese: natural, native-level business Japanese. Use real financial/regulatory \
terminology (資金決済法, 金商法, ステーブルコイン, RWA, カストディ). NOT textbook-simplified.
- Korean: casual-professional (반말 OK). Like explaining to a colleague. \
Translate EVERYTHING — no omissions or summaries.
- The reader reads English first, then checks Japanese for language practice, \
then Korean if stuck.\
"""

ISSUE_PROMPT = """\
Produce a complete Rails issue from the news items below. Follow this \
structure exactly:

First line MUST be:
MAIN_TITLE: [concise English title of the single most important story, ≤8 words]

HEADER:
# Rails — Issue #{issue_number}
{date_line} · Heechang's daily journal on the future of financial infrastructure

SECTION 1 — THREE DEEP READS:
Pick the 3 most consequential stories for financial infrastructure from the \
last 24 hours. Bias toward: stablecoins, RWA & tokenization, custody & \
settlement infra, Asia regulatory developments, institutional adoption, \
payment rails. De-prioritize token price action, retail narratives, NFT/meme.

For EACH of the three, translate PARAGRAPH BY PARAGRAPH — output each \
subsection in EN → JP → KR before moving to the next subsection:

N. [Headline as single declarative sentence]

What happened. [English, 2-3 sentences]
🇯🇵 日本語:
[Japanese translation of What happened]
📝 한국어 번역:
[Korean translation of What happened]

What it means. [English, 4-6 sentences]
🇯🇵 日本語:
[Japanese translation of What it means]
📝 한국어 번역:
[Korean translation of What it means]

Infra implication. [English, 2-4 sentences]
🇯🇵 日本語:
[Japanese translation of Infra implication]
📝 한국어 번역:
[Korean translation of Infra implication]

Open question. [English, 1 sentence]
🇯🇵 日本語:
[Japanese translation]
📝 한국어 번역:
[Korean translation. Then add: 왜 중요한가: 1-2 sentences if relevant.]

SECTION 2 — THE SWEEP:
8-12 headlines grouped by region:
Americas / Asia / Europe / Infra & markets
Skip a group if nothing meaningful. Don't pad.

For EACH headline, output all three languages together before moving to \
the next headline:

[English headline]
▸ Explanation: What happened in 1 sentence.
▸ Implication: Why it matters for financial infra in 1 sentence.

🇯🇵 日本語:
[Japanese translation of the headline + both bullet points above]

📝 한국어 번역:
[Korean translation of the headline + both bullet points above]

Then move to the next headline and repeat the same EN → JP → KR pattern.

SECTION 3 — FOOD FOR THOUGHT:
Today is {weekday}. Today's rotation: {rotation_slot}.
{rotation_instructions}

After the English content, add:
🇯🇵 日本語:
[Full Japanese translation]
📝 한국어 번역:
[Full Korean translation]

CLOSING:
Single italicized line: issue number, estimated minutes elapsed, \
one-line teaser for tomorrow's rotation ({tomorrow_slot}).

LENGTH: English content should be 900-1,300 words. Japanese and Korean \
translations will add to the total — that is expected.

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


def generate_issue(news_items: list[dict]) -> tuple[str, str]:
    """Call Anthropic Claude to produce the Rails issue.

    Returns (main_title, issue_text) where main_title is the extracted
    headline for use in the [Finance Infra #NN] (main_title) format.
    """
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
        model="claude-sonnet-4-6",
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text

    # Extract the MAIN_TITLE line from the top of the response
    main_title = "Finance Infra"
    lines = raw.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("MAIN_TITLE:"):
            main_title = line[len("MAIN_TITLE:"):].strip().strip('"').strip("'")
            body_start = i + 1
            break

    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    issue_text = "\n".join(lines[body_start:])

    return main_title, issue_text


# ── Google Calendar ──────────────────────────────────────────────────────────
def get_calendar_service():
    """Build a Calendar API client from the service-account JSON env var."""
    sa_info = json.loads(GCP_SA_KEY)
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=SCOPES
    )
    return build("calendar", "v3", credentials=creds)


def _issue_title(main_title: str) -> str:
    """Format the standard [Finance Infra #NN] (main_title) title string."""
    return f"[Finance Infra #{ISSUE_NUMBER}] ({main_title})"


def create_calendar_event(issue_text: str, main_title: str = "Finance Infra") -> str:
    """Insert a 30-min event at 09:00 KST with the issue as description."""
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


def _rich_text(content: str) -> dict:
    """Build a single Notion rich-text object."""
    return {"type": "text", "text": {"content": content[:2000]}}


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
    """Convert the Rails newsletter plain text into Notion blocks.

    Preserves original structure and content as-is. Only applies:
    - H2 for section headers (no background color)
    - H3 for numbered deep-read headlines (no background color)
    - Bulleted list items for ▸ lines
    - Divider blocks for ━━━ lines
    - Everything else stays as plain paragraph text.
    """
    blocks = []

    for line in text.split("\n"):
        stripped = line.strip()

        # Empty lines → skip
        if not stripped:
            continue

        # Divider lines (━━━)
        if _is_divider(stripped):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            continue

        # Section headers (ALL CAPS) → H2, no background
        if _is_section_header(stripped):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [_rich_text(stripped)],
                    "is_toggleable": False,
                },
            })
            continue

        # Numbered headlines (1. 2. 3.) → H3, no background
        if len(stripped) > 2 and stripped[0].isdigit() and stripped[1] == ".":
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [_rich_text(stripped)],
                    "is_toggleable": False,
                },
            })
            continue

        # Bullet lines (▸) → bulleted list items
        if stripped.startswith("▸"):
            bullet_text = stripped.lstrip("▸").strip()
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [_rich_text(bullet_text)]},
            })
            continue

        # 🇯🇵 Japanese translation marker → callout
        if stripped in ("🇯🇵 日本語:", "🇯🇵 日本語", "🇯🇵日本語:", "🇯🇵日本語"):
            blocks.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [_rich_text("日本語")],
                    "icon": {"emoji": "🇯🇵"},
                },
            })
            continue

        # 📝 Korean translation marker → callout
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

        # Everything else → plain paragraph
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [_rich_text(stripped)]},
        })

    return blocks


def create_notion_page(issue_text: str, main_title: str = "Finance Infra") -> tuple[str, str]:
    """Create a Notion page. Returns (url, page_id)."""
    if not NOTION_TOKEN:
        print("  ⚠ NOTION_TOKEN not set, skipping Notion.")
        return "", ""

    now_kst = datetime.now(KST)
    title = _issue_title(main_title)

    # Notion API limits children to 100 blocks per request
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

    # Append remaining blocks in batches of 100 if needed
    for i in range(100, len(all_blocks), 100):
        batch = all_blocks[i:i+100]
        append_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        r = requests.patch(append_url, headers=headers, json={"children": batch}, timeout=30)
        r.raise_for_status()

    return page.get("url", ""), page_id


# ── Furigana Reading Aids ────────────────────────────────────────────────────
_FURIGANA_SYSTEM = """\
あなたは日本語のふりがな付与の専門家です。与えられた日本語テキストに正確なふりがなを付けてください。"""

_FURIGANA_PROMPT = """\
以下の日本語段落それぞれにふりがなを付けてください。

ルール:
1. 漢字はそのまま残し、直後に丸括弧でひらがな読みを付ける。
   例: 議員連盟（ぎいんれんめい）、暗号資産（あんごうしさん）
2. カタカナ・数字・ラテン文字・句読点・記号はそのまま残す。
3. 送り仮名を正しく処理する。
   例: 求（もと）める、基（もと）づく、円建（えんだ）て
4. 元のテキストにすでに読みが括弧で示されている場合はそのまま維持する。
5. 固有名詞（人名・社名・地名）にもふりがなを付ける。
6. 各段落を [番号] で区切って返す。余計な説明は付けない。

{paragraphs}
"""


def _has_japanese_chars(text: str) -> bool:
    return any(
        "\u3040" <= c <= "\u309f" or "\u30a0" <= c <= "\u30ff"
        for c in text
    )


def _has_korean_chars(text: str) -> bool:
    return any("\uac00" <= c <= "\ud7af" for c in text)


def _is_jp_body(text: str) -> bool:
    if not text or _has_korean_chars(text) or not _has_japanese_chars(text):
        return False
    if text.startswith("왜 "):
        return False
    return True


def _block_plain_text(block: dict) -> str:
    btype = block["type"]
    rt = block.get(btype, {}).get("rich_text", [])
    return "".join(t.get("plain_text", "") for t in rt)


def _fetch_page_blocks(page_id: str) -> list[dict]:
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
    }
    blocks: list[dict] = []
    cursor = None
    while True:
        url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
        if cursor:
            url += f"&start_cursor={cursor}"
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        blocks.extend(data["results"])
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]
    return blocks


def _find_furigana_targets(blocks: list[dict]) -> list[tuple[int, str, str]]:
    """Find Japanese paragraphs between a 🇯🇵 callout and a 📝 callout."""
    targets: list[tuple[int, str, str]] = []
    n = len(blocks)
    i = 0
    while i < n:
        b = blocks[i]
        btype = b["type"]
        text = _block_plain_text(b)

        # After a 🇯🇵 callout, collect JP paragraphs until 📝 callout or divider
        if btype == "callout":
            icon = b.get("callout", {}).get("icon", {}).get("emoji", "")
            if icon == "🇯🇵":
                i += 1
                while i < n:
                    bb = blocks[i]
                    bt = bb["type"]
                    tt = _block_plain_text(bb)
                    # Stop at next callout, divider, or heading
                    if bt in ("callout", "divider") or bt.startswith("heading"):
                        break
                    if bt == "paragraph" and _is_jp_body(tt):
                        targets.append((i, bb["id"], tt))
                    elif bt == "bulleted_list_item" and _is_jp_body(tt):
                        targets.append((i, bb["id"], tt))
                    i += 1
                continue

        i += 1
    return targets


def _generate_furigana_batch(
    paragraphs: list[tuple[int, str, str]],
) -> dict[int, str]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    parts = [f"[{idx}]\n{text}" for idx, (_, _, text) in enumerate(paragraphs)]
    prompt = _FURIGANA_PROMPT.format(paragraphs="\n\n".join(parts))
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=20000,
        system=_FURIGANA_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text
    results: dict[int, str] = {}
    cur_idx: int | None = None
    cur_lines: list[str] = []
    for line in raw.split("\n"):
        stripped = line.strip()
        if stripped.startswith("[") and "]" in stripped:
            try:
                idx = int(stripped[1:stripped.index("]")])
                if cur_idx is not None:
                    results[cur_idx] = "\n".join(cur_lines).strip()
                cur_idx = idx
                cur_lines = []
                rest = stripped[stripped.index("]") + 1:].strip()
                if rest:
                    cur_lines.append(rest)
            except ValueError:
                cur_lines.append(line)
        elif cur_idx is not None:
            cur_lines.append(line)
    if cur_idx is not None:
        results[cur_idx] = "\n".join(cur_lines).strip()
    return results


def _insert_notion_toggle(
    page_id: str, after_block_id: str, furigana: str,
) -> None:
    chunks = []
    remaining = furigana
    while len(remaining) > 2000:
        chunks.append(remaining[:2000])
        remaining = remaining[2000:]
    chunks.append(remaining)
    children = [
        {
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": c}}],
            },
        }
        for c in chunks
    ]
    toggle = {
        "type": "toggle",
        "toggle": {
            "rich_text": [
                {"type": "text", "text": {"content": "ふりがな（ひらがな）"}},
            ],
            "children": children,
        },
    }
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    r = requests.patch(
        url, headers=headers, json={"children": [toggle], "after": after_block_id},
        timeout=30,
    )
    r.raise_for_status()


def add_furigana_to_page(page_id: str) -> int:
    """Add furigana toggles to Japanese paragraphs on a Notion page."""
    print("▸ Adding furigana reading aids...")
    blocks = _fetch_page_blocks(page_id)
    targets = _find_furigana_targets(blocks)
    print(f"  {len(targets)} Japanese paragraphs found.")
    if not targets:
        return 0
    furigana_map = _generate_furigana_batch(targets)
    print(f"  Furigana generated for {len(furigana_map)}/{len(targets)} paragraphs.")
    inserted = 0
    for idx in reversed(range(len(targets))):
        _, block_id, _ = targets[idx]
        furigana = furigana_map.get(idx)
        if not furigana:
            continue
        _insert_notion_toggle(page_id, block_id, furigana)
        inserted += 1
        time.sleep(0.35)
    print(f"  ✓ {inserted} furigana toggles inserted.")
    return inserted


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
    main_title, issue_text = generate_issue(items_for_llm)
    print(f"  Title: [Finance Infra #{ISSUE_NUMBER}] ({main_title})")

    print("▸ Creating Google Calendar event...")
    event_link = create_calendar_event(issue_text, main_title)
    print(f"✓ Event created: {event_link}")

    print("▸ Saving to Notion...")
    notion_url, notion_page_id = create_notion_page(issue_text, main_title)
    if notion_url:
        print(f"✓ Notion page created: {notion_url}")

    # Add furigana reading aids to the Japanese sections
    if notion_page_id:
        try:
            add_furigana_to_page(notion_page_id)
        except Exception as e:
            print(f"  ⚠ Furigana step failed (non-fatal): {e}")


if __name__ == "__main__":
    run()
