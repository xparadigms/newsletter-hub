#!/usr/bin/env python3
"""Japan Briefing — Bi-weekly bilingual newsletter → Google Calendar + Notion.

Scrapes Japan crypto/regulation/real-estate news from Japanese and English
sources, generates a bilingual (JP body + KR translation) issue via Claude,
and inserts a calendar event + Notion page.
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
    # Japanese general / finance / real estate / architecture
    "NHK News": "https://www3.nhk.or.jp/rss/news/cat0.xml",
    "ITmedia": "https://rss.itmedia.co.jp/rss/2.0/itmedia_all.xml",
    "ArchDaily": "https://www.archdaily.com/feed",
    "Dezeen": "https://www.dezeen.com/feed/",
    "Timeout Tokyo": "https://www.timeout.jp/tokyo/ja/rss",
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
    # Architecture / urban design / real estate
    "再開発", "redevelopment", "不動産", "real estate",
    "容積率", "FAR", "都市計画", "urban planning",
    "マンション", "タワー", "tower", "ヒルズ", "Hills",
    "渋谷", "Shibuya", "六本木", "Roppongi", "麻布", "Azabudai",
    "虎ノ門", "Toranomon", "品川", "Shinagawa",
    "建築", "architect", "設計", "design",
    "隈研吾", "Kengo Kuma", "安藤忠雄", "Tadao Ando",
    "妹島和世", "SANAA", "丹下健三", "Kenzo Tange",
    "TOKYO TORCH", "新建築", "ArchDaily", "Dezeen",
    "ファサード", "facade", "インテリア", "interior",
    # Food / lifestyle
    "グルメ", "レストラン", "restaurant", "食べログ",
    "ラーメン", "寿司", "sushi", "居酒屋", "izakaya",
    "カフェ", "café", "ミシュラン", "Michelin",
    "食ベログ", "Tabelog", "Timeout",
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
Japan's crypto regulation, stablecoin infrastructure, architecture & urban \
design, food, and lifestyle, written for Heechang — co-founder/CSO at \
Four Pillars, Seoul-based institutional crypto research firm backed by \
Pantera/Kakao Ventures/Hashed.

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
- Tokyo's architecture and private-led redevelopment is 10 years ahead of Seoul

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

First line MUST be:
MAIN_TITLE: [concise English title of the single most important story, ≤8 words]

HEADER:
━━━━━━━━━━━━━━━━━━━━━━━━━━
JAPAN BRIEFING — Issue #{issue_number}
{date_line} · 日本クリプト・不動産ブリーフィング
━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION 1 — 日本クリプト・規制ウォッチ (JAPAN CRYPTO & REGULATION WATCH):
Pick 3-4 most consequential Japan crypto/stablecoin/regulation stories.
For EACH story:
【見出し】 Headline in Japanese
Japanese body (3-4 sentences, cite sources, use real terminology)
📝 한국어 번역:
Full Korean translation of EVERY sentence above (do NOT summarize or shorten).
Then add: 왜 중요한가: [1-2 sentences connecting to ASA/ASC/FP work]

SECTION 2 — 建築・都市デザイン (ARCHITECTURE & URBAN DESIGN):
2-3 stories on Tokyo/Japan architecture and urban design. Focus on: \
landmark buildings and design philosophy (麻布台ヒルズ, 虎ノ門ヒルズ, TOKYO TORCH), \
architect profiles (隈研吾, 安藤忠雄, 妹島和世), design details, materials, \
structural innovation, public space design. Same bilingual format.
"What makes Tokyo's built environment world-class" angle.

SECTION 3 — 東京グルメ・発見 (TOKYO FOOD & FINDS):
Two food or dining recommendations: trending restaurant, seasonal dish, \
hidden spot, new opening, or food trend. 3-4 sentences each JP + KR. \
Include neighborhood and price range if relevant.

SECTION 4 — 今週の話題 (THIS WEEK'S BUZZ):
Two things Japanese people are actually talking about this week: viral topic \
on X/Twitter Japan, trending show, lifestyle trend, seasonal event, \
or cultural moment. 3-4 sentences each JP + KR. Snapshot, not analysis.

SECTION 5 — 今週の日本語表現 (JAPANESE EXPRESSION OF THE WEEK):
📖 今週の表現: [expression]
読み方: [reading]
意味: [Korean meaning]
例文: [Japanese example]
→ [Korean translation]

CLOSING:
━━━━━━━━━━━━━━━━━━━━━━━━━━
Issue #{issue_number} · 次号: {next_issue_date}
[One-line teaser JP + KR]
━━━━━━━━━━━━━━━━━━━━━━━━━━

LENGTH: 2,200-3,300 words total.

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


def generate_issue(news_items: list[dict]) -> tuple[str, str]:
    """Call Anthropic Claude to produce the Japan Briefing issue.

    Returns (main_title, issue_text) where main_title is the extracted
    headline for use in the [Japan Brief #NN] (main_title) format.
    """
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
        max_tokens=12000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text

    # Extract the MAIN_TITLE line from the top of the response
    main_title = "Japan Brief"
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
    """Format the standard [Japan Brief #NN] (main_title) title string."""
    return f"[Japan Brief #{ISSUE_NUMBER}] ({main_title})"


def create_calendar_event(issue_text: str, main_title: str = "Japan Brief") -> str:
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
_SECTION_HEADER_EXACT = [
    "SECTION 1",
    "SECTION 2",
    "SECTION 3",
    "SECTION 4",
    "SECTION 5",
    "JAPAN CRYPTO & REGULATION WATCH",
    "ARCHITECTURE & URBAN DESIGN",
    "TOKYO FOOD & FINDS",
    "THIS WEEK'S BUZZ",
    "JAPANESE EXPRESSION OF THE WEEK",
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
        # 📝 marker line — skip (Korean text follows as a plain paragraph)
        if stripped in ("📝 한국어 번역:", "📝 한국어 번역", "📝 한국어번역:", "📝 한국어번역"):
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


def create_notion_page(issue_text: str, main_title: str = "Japan Brief") -> tuple[str, str]:
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        print("  ⚠ NOTION_TOKEN or NOTION_DATABASE_ID not set, skipping Notion.")
        return "", ""

    now_kst = datetime.now(KST)
    title = _issue_title(main_title)
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
   例: 鮎（アユ）はそのまま鮎（アユ）とする。
5. 固有名詞（人名・社名・地名）にもふりがなを付ける。
   例: 隈研吾（くまけんご）、堀田丸正（ほったまるしょう）
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
    """True for Japanese body content (not Korean, not empty)."""
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
    """Fetch every top-level block from a Notion page."""
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
    """Identify JP body paragraphs, Section 5 例文, and closing teaser."""
    targets: list[tuple[int, str, str]] = []
    n = len(blocks)
    i = 0
    while i < n:
        b = blocks[i]
        btype = b["type"]
        text = _block_plain_text(b)

        # Story pattern: heading_3【…】 → KR translation → JP body → callout
        if btype == "heading_3" and text.startswith("【"):
            i += 1
            if i < n:
                nxt = _block_plain_text(blocks[i])
                if nxt.startswith("(") and _has_korean_chars(nxt):
                    i += 1
            while i < n:
                bb = blocks[i]
                bt = bb["type"]
                tt = _block_plain_text(bb)
                if bt in ("callout", "divider") or bt.startswith("heading"):
                    break
                if bt == "paragraph" and _is_jp_body(tt):
                    targets.append((i, bb["id"], tt))
                i += 1
            continue

        # Section 5: 例文 line
        if btype == "paragraph" and text.startswith("例文") and _has_japanese_chars(text):
            targets.append((i, b["id"], text))
            i += 1
            continue

        # Closing JP teaser
        if btype == "paragraph" and i >= n - 5:
            if _is_jp_body(text) and not text.startswith("Issue ") and "次号" not in text:
                targets.append((i, b["id"], text))

        i += 1
    return targets


def _generate_furigana_batch(
    paragraphs: list[tuple[int, str, str]],
) -> dict[int, str]:
    """Call Claude to produce furigana for all paragraphs at once."""
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
    """Insert a collapsed toggle block with furigana text."""
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
    """Add furigana toggles to a Notion page. Returns count inserted."""
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
        _, block_id, text = targets[idx]
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
    main_title, issue_text = generate_issue(items_for_llm)
    print(f"  Title: [Japan Brief #{ISSUE_NUMBER}] ({main_title})")

    print("▸ Creating Google Calendar event...")
    try:
        event_link = create_calendar_event(issue_text, main_title)
        if event_link:
            print(f"✓ Event created: {event_link}")
    except Exception as e:
        print(f"  ⚠ Calendar failed (non-fatal): {e}")

    print("▸ Saving to Notion...")
    notion_url, notion_page_id = create_notion_page(issue_text, main_title)
    if notion_url:
        print(f"✓ Notion page created: {notion_url}")

    # Add furigana reading aids to the Notion page
    if notion_page_id:
        try:
            add_furigana_to_page(notion_page_id)
        except Exception as e:
            print(f"  ⚠ Furigana step failed (non-fatal): {e}")

    # Also print the issue to stdout for debugging
    print("\n" + "=" * 60)
    print(issue_text)
    print("=" * 60)


if __name__ == "__main__":
    run()
