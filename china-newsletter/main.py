#!/usr/bin/env python3
"""China Daily — politics, tech, and what China is talking about → Supabase.

Scrapes Chinese-language and China-desk news, writes a short-paragraph issue in
Simplified Chinese with a Korean translation per story, segments each sentence
into words with pinyin, and stores it.

Supabase-only. Unlike the other four generators there is no Notion mirror and no
calendar event: the site reads Supabase now, so a second copy would be a
liability rather than an archive.
"""

import os
import pathlib
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import anthropic
import feedparser
import requests
from bs4 import BeautifulSoup

# The workflow runs with this project as the working directory, so the repo root
# is not importable. Python only puts the *script's* directory on sys.path.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import blocks as china_blocks  # noqa: E402
from shared import issue as issue_row, store  # noqa: E402

# ── Config ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Seoul")
KST = timezone(timedelta(hours=9))
ISSUE_NUMBER = int(os.environ.get("ISSUE_NUMBER", "1"))

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 12000

# ── Sources ─────────────────────────────────────────────────────────────────
# The risk here is not that mainland sites are blocked from us — the runner sits
# outside China — but that they reject datacentre IPs, and that most official
# outlets killed their RSS years ago. Google News aggregates mainland and
# overseas Chinese media and answers reliably, so it is the floor: if every
# other feed 403s, these four alone still carry an issue.
_GNEWS = "https://news.google.com/rss/search?q={q}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
GOOGLE_NEWS_QUERIES = ["中国 政策", "中国 经济", "中国 科技", "中国 社会 热点"]

RSS_FEEDS = {
    # Chinese-language, hosted outside the mainland, reliably reachable.
    "BBC 中文": "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml",
    "DW 中文": "https://rss.dw.com/rdf/rss-chi-all",
    "联合早报": "https://www.zaobao.com/realtime/china/rss.xml",
    # English China desks — facts the model then writes up in Chinese.
    "SCMP China": "https://www.scmp.com/rss/4/feed",
    "Nikkei Asia": "https://asia.nikkei.com/rss",
    # Mainland-hosted. These 403 or return empty to datacentre IPs often enough
    # that they must never be load-bearing; the per-feed try/except covers it.
    "36氪": "https://36kr.com/feed",
    "少数派": "https://sspai.com/feed",
}

TELEGRAM_CHANNELS = ["https://t.me/s/tnews365"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _entries(name: str, url: str, limit: int, cutoff: datetime) -> list[dict]:
    items: list[dict] = []
    feed = feedparser.parse(url)
    for entry in feed.entries[:limit]:
        published = None
        for attr in ("published_parsed", "updated_parsed"):
            parsed = getattr(entry, attr, None)
            if parsed:
                published = datetime(*parsed[:6], tzinfo=KST)
                break
        if published and published < cutoff:
            continue
        title = getattr(entry, "title", "")
        summary = getattr(entry, "summary", "")
        if not title:
            continue
        items.append(
            {
                "source": name,
                "text": f"{title}. {summary}" if summary else title,
                "url": getattr(entry, "link", ""),
                "date": published.isoformat() if published else "",
            }
        )
    return items


def scrape_google_news() -> list[dict]:
    """The floor. Failure here is worth stopping for; the rest is optional."""
    items: list[dict] = []
    cutoff = datetime.now(KST) - timedelta(hours=36)
    for query in GOOGLE_NEWS_QUERIES:
        try:
            items.extend(
                _entries(f"Google News/{query}", _GNEWS.format(q=quote(query)), 25, cutoff)
            )
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ Google News '{query}' failed: {e}")
    return items


def scrape_rss_feeds() -> list[dict]:
    items: list[dict] = []
    cutoff = datetime.now(KST) - timedelta(hours=36)
    for name, url in RSS_FEEDS.items():
        try:
            found = _entries(name, url, 30, cutoff)
            items.extend(found)
            if not found:
                print(f"  ⚠ {name} returned nothing (mainland feeds often do)")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ Failed to parse {name}: {e}")
    return items


def scrape_telegram_channels() -> list[dict]:
    items: list[dict] = []
    for channel in TELEGRAM_CHANNELS:
        try:
            resp = requests.get(channel, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for widget in soup.select("div.tgme_widget_message_wrap"):
                el = widget.select_one("div.tgme_widget_message_text")
                if not el:
                    continue
                text = el.get_text(separator=" ", strip=True)
                if text:
                    link = el.select_one("a[href]")
                    items.append(
                        {
                            "source": "Telegram",
                            "text": text,
                            "url": link["href"] if link else "",
                            "date": "",
                        }
                    )
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ Failed to scrape {channel}: {e}")
    return items


def dedupe(items: list[dict]) -> list[dict]:
    seen_urls: set[str] = set()
    seen_text: set[str] = set()
    out = []
    for item in items:
        url = item.get("url", "")
        key = item["text"][:60]
        if (url and url in seen_urls) or key in seen_text:
            continue
        if url:
            seen_urls.add(url)
        seen_text.add(key)
        out.append(item)
    return out


# ── Prompt ──────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are the writer of "China Daily", a daily Chinese-language brief written for \
Heechang — co-founder/CSO at Four Pillars, a Seoul-based institutional crypto \
research firm. He reads Chinese at an intermediate level and uses this brief \
both as a news source and as reading practice.

Cover three things: Chinese politics and policy, Chinese technology and \
industry, and whatever ordinary people in China are actually talking about \
this week. Balance them; do not let policy crowd out the rest.

Voice: plain, factual, concrete. Name the institution, the number, the date. \
No editorialising, no filler, no hedging. This is a brief, not an essay.

Write in natural Simplified Chinese at roughly HSK 5 level: real news register, \
not textbook sentences, but avoid rare literary idiom where a common word will \
do. Korean translations are casual-professional — the way you would explain the \
story to a colleague.
"""

ISSUE_PROMPT = """\
Write today's China Daily issue from the news items below. Today is {date_line}.

Output format — these three markers and nothing else. No Markdown, no emoji, no \
bullet characters, no horizontal rules.

Line 1 must be:
SUMMARY: <one Korean sentence, at most 60 characters, summarising the day>

Line 2 must be:
MAIN_TITLE: <English title of the single most important story, 8 words or fewer>

Then 6 to 8 stories. Each story is exactly:

### <headline in Korean>
<Chinese sentence line>
<Chinese sentence line>
> <Korean translation of every Chinese line in this story>

Rules that matter:

- The ### headline is written in KOREAN and is NOT numbered. Do not write "1.", \
"2." or any ordinal — numbering is added afterwards.
- Each line under a ### is one to three Chinese sentences and at most 60 \
characters. Break longer thoughts across several lines. Two to four lines per \
story.
- Write ONLY Simplified Chinese in those lines. No Traditional characters.
- NEVER write pinyin or romanisation anywhere, and never put a reading in \
parentheses after a word. Readings are added afterwards by a separate tool, and \
anything you add corrupts it.
- Exactly one > line per story, at the end. It translates every Chinese line in \
that story into Korean — a full translation, not a summary.
- Do not repeat a story. Do not invent facts, numbers or dates that are not in \
the items below.

--- NEWS ITEMS ---
{news_items}
"""


def generate_issue(items: list[dict]) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    now = datetime.now(KST)
    news = "\n\n".join(
        f"[{i['source']}] {i['text'][:400]}" + (f"\n  URL: {i['url']}" if i["url"] else "")
        for i in items
    )
    prompt = ISSUE_PROMPT.format(
        date_line=now.strftime("%A, %B %d, %Y"), news_items=news
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def _issue_title(main_title: str) -> str:
    return f"[China Daily #{ISSUE_NUMBER}] ({main_title})"


# ── Main ────────────────────────────────────────────────────────────────────
def run():
    now_kst = datetime.now(KST)
    print(f"▸ China Daily — Issue #{ISSUE_NUMBER}")
    print(f"  {now_kst.strftime('%A, %B %d, %Y')}")

    print("▸ Scraping Google News (zh-CN)...")
    google_items = scrape_google_news()
    print(f"  Found {len(google_items)} items.")

    print("▸ Scraping other feeds...")
    other = scrape_rss_feeds() + scrape_telegram_channels()
    print(f"  Found {len(other)} items.")

    items = dedupe(google_items + other)
    if len(items) < 8:
        # Publishing a thin issue is worse than publishing none: it would take
        # the slug for the day and a rerun would keep the sparse URL.
        print(f"✗ Only {len(items)} usable items — too thin to publish.")
        sys.exit(1)
    items = items[:60]
    print(f"  {len(items)} items after dedupe.")

    print(f"▸ Generating issue via Claude ({len(items)} items)...")
    issue_text = generate_issue(items)

    main_title, summary = china_blocks.parse_meta(issue_text)
    print(f"  Title: {_issue_title(main_title)}")

    print("▸ Segmenting Chinese and attaching pinyin...")
    blocks, stories, unsegmented = china_blocks.build_blocks(issue_text)
    print(f"  {stories} stories, {len(blocks)} blocks, {unsegmented} lines unsegmented.")
    if stories == 0:
        print("✗ No ### headings found — the model ignored the output contract.")
        sys.exit(1)
    if unsegmented > max(2, stories):
        # A handful of odd lines is tolerable; a systematic failure means the
        # model emitted something other than plain Simplified Chinese.
        print(f"✗ {unsegmented} lines failed segmentation — refusing to publish.")
        sys.exit(1)

    date_str = now_kst.strftime("%Y-%m-%d")
    row = issue_row.build_row_from_blocks(
        section="china",
        issue_date=date_str,
        raw_title=_issue_title(main_title),
        blocks=blocks,
        source_text=issue_text,
        source_format="china_md",
        summary=summary,
    )

    print("▸ Saving to Supabase...")
    stored = store.upsert_issue(row)
    if stored.get("slug"):
        print(f"✓ Stored: china/{stored['slug']}")
        store.ping_revalidate("china", stored["slug"])

    print("\n" + "=" * 60)
    print(issue_text)
    print("=" * 60)


if __name__ == "__main__":
    run()
