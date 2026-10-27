"""The hourly news feed: what each newsletter's sources are saying now.

    python -m shared.news_feed [--dry-run]

Each newsletter reads a set of feeds once a day to write its issue. This reads
the same kind of feeds every hour and keeps the headlines themselves — title,
source, a line of summary, a picture — in `feed_items`, which the Feed tab on
the site and in the app shows, newest first, filterable by newsletter.

Only headlines and links are kept; the article stays on its publisher's site.
New items get their picture from the feed itself, or failing that the page's
own preview image (shared/covers.py). Items older than 30 days are deleted.
"""

from __future__ import annotations

import argparse
import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
import requests

from . import covers, http, store

# The feeds behind each newsletter, as its generator reads them, plus a few
# for the newsletters whose generators search rather than subscribe. Mandarin
# Basics is a lesson, not news, so it has no feed.
FEEDS: dict[str, dict[str, str]] = {
    "startup": {
        "TechCrunch": "https://techcrunch.com/feed/",
        "TechCrunch Venture": "https://techcrunch.com/category/venture/feed/",
        "Crunchbase News": "https://news.crunchbase.com/feed/",
        "The Verge": "https://www.theverge.com/rss/index.xml",
    },
    "business": {
        "Stratechery": "https://stratechery.com/feed/",
        "SaaStr": "https://www.saastr.com/feed/",
        "Lenny's Newsletter": "https://lennysnewsletter.com/feed",
        "a16z Podcast": "https://feeds.simplecast.com/JGE3yC0V",
        "Invest Like the Best": "https://feeds.megaphone.fm/investlikethebest",
    },
    "fintech": {
        "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "The Block": "https://www.theblock.co/rss.xml",
        "DL News": "https://www.dlnews.com/arc/outboundfeeds/rss/",
        "PYMNTS": "https://www.pymnts.com/feed/",
        "Finextra": "https://www.finextra.com/rss/headlines.aspx",
        "Payments Dive": "https://www.paymentsdive.com/feeds/news/",
        "Banking Dive": "https://www.bankingdive.com/feeds/news/",
        "Fintech Futures": "https://www.fintechfutures.com/feed/",
    },
    "stocks": {
        "CNBC Markets": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
        "Investing.com": "https://www.investing.com/rss/news_25.rss",
    },
    "china": {
        "BBC 中文": "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml",
        "DW 中文": "https://rss.dw.com/rdf/rss-chi-all",
        "SCMP China": "https://www.scmp.com/rss/4/feed",
        "36氪": "https://www.36kr.com/feed",
        "少数派": "https://sspai.com/feed",
    },
    "japan": {
        "Yahoo 主要": "https://news.yahoo.co.jp/rss/topics/top-picks.xml",
        "Yahoo 経済": "https://news.yahoo.co.jp/rss/topics/business.xml",
        "Yahoo IT": "https://news.yahoo.co.jp/rss/topics/it.xml",
        "ITmedia": "https://rss.itmedia.co.jp/rss/2.0/itmedia_all.xml",
        "GIGAZINE": "https://gigazine.net/news/rss_2.0/",
    },
    "watch": {
        "Hodinkee": "https://www.hodinkee.com/articles.rss",
        "Fratello": "https://www.fratellowatches.com/feed/",
        "Monochrome": "https://monochrome-watches.com/feed/",
        "aBlogtoWatch": "https://www.ablogtowatch.com/feed/",
        "Watches by SJX": "https://watchesbysjx.com/feed/",
    },
}

# An hourly run only needs what is new, but a feed that was down for a while
# should not lose its backlog: anything from the last two days is considered.
WINDOW = timedelta(hours=48)
KEEP = timedelta(days=30)
TABLE = "feed_items"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TheBrief/1.0; +https://heechang-newsletter.vercel.app)"}

TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str, limit: int) -> str:
    text = html.unescape(TAG_RE.sub(" ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def _when(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def _image(entry: Any) -> str | None:
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key) or []:
            if m.get("url") and not m.get("url", "").endswith(".mp3"):
                return m["url"]
    for link in entry.get("links") or []:
        if link.get("rel") == "enclosure" and (link.get("type") or "").startswith("image"):
            return link.get("href")
    found = re.search(r'<img[^>]+src=["\']([^"\']+)', entry.get("summary") or "")
    return found.group(1) if found else None


def collect_section(section: str) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []
    for source, url in FEEDS[section].items():
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            feed = feedparser.parse(resp.content)
        except Exception as e:  # noqa: BLE001 — one dead feed must not stop the rest
            print(f"  ⚠ {section}/{source}: {e}")
            continue
        n = 0
        for entry in feed.entries[:40]:
            link = (entry.get("link") or "").strip()
            title = _clean(entry.get("title") or "", 300)
            if not link.startswith("http") or not title:
                continue
            when = _when(entry) or now
            if now - when > WINDOW:
                continue
            items.append({
                "section": section,
                "url": link,
                "title": title,
                "source": source,
                "summary": _clean(entry.get("summary") or entry.get("description") or "", 320) or None,
                "image_url": _image(entry),
                "published_at": min(when, now).isoformat(),
            })
            n += 1
        print(f"  {section}/{source}: {n}")
    return items


def _existing(urls: list[str]) -> set[str]:
    base, key = store._config()
    known: set[str] = set()
    for i in range(0, len(urls), 80):
        chunk = urls[i : i + 80]
        quoted = ",".join('"' + u.replace('"', '\\"') + '"' for u in chunk)
        resp = http.request_with_retry(
            "GET", f"{base}/rest/v1/{TABLE}", label="Supabase", headers=store._headers(key),
            params={"select": "url", "url": f"in.({quoted})"},
        )
        resp.raise_for_status()
        known |= {r["url"] for r in resp.json()}
    return known


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with ThreadPoolExecutor(max_workers=len(FEEDS)) as pool:
        items = [i for batch in pool.map(collect_section, FEEDS) for i in batch]
    # One row per URL, even when two feeds carry the same story.
    unique = list({i["url"]: i for i in items}.values())
    print(f"{len(unique)} item(s) in the last {int(WINDOW.total_seconds() // 3600)}h")
    if args.dry_run:
        for i in unique[:15]:
            print(f"  [{i['section']}] {i['source']}: {i['title'][:80]} {'🖼' if i['image_url'] else ''}")
        return 0

    fresh = [i for i in unique if i["url"] not in _existing([i["url"] for i in unique])]
    # A picture for the new ones that came without, from the page itself.
    need = [i for i in fresh if not i["image_url"]][:120]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for item, image in zip(need, pool.map(lambda i: covers._og_image(i["url"]), need)):
            item["image_url"] = image

    base, key = store._config()
    for i in range(0, len(fresh), 200):
        resp = http.request_with_retry(
            "POST", f"{base}/rest/v1/{TABLE}?on_conflict=url", label="Supabase",
            headers=store._headers(key, "resolution=ignore-duplicates,return=minimal"),
            json=fresh[i : i + 200],
        )
        resp.raise_for_status()

    cutoff = (datetime.now(timezone.utc) - KEEP).isoformat()
    resp = http.request_with_retry(
        "DELETE", f"{base}/rest/v1/{TABLE}", label="Supabase",
        headers=store._headers(key, "return=minimal"), params={"published_at": f"lt.{cutoff}"},
    )
    resp.raise_for_status()
    print(f"{len(fresh)} new item(s) stored; {sum(1 for i in fresh if i['image_url'])} with a picture.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
