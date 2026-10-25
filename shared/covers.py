"""A cover image for each issue.

The image is the one the issue's own source already offers for link previews
— the og:image that Messages or Slack would show for that link — so it is
about the story, not decoration. Issues without a source link (China Daily,
Mandarin Basics) get a freely licensed photo from Openverse instead, searched
by the headline, with its credit kept so the clients can show it.

Stored on the row as `cover`: {"url", "credit", "link", "kind"}. The clients
hotlink the URL rather than this copying anyone's image. Non-fatal throughout:
an issue with no cover is still an issue, shown on its typographic card.
"""

from __future__ import annotations

import hashlib
import html
import re
from typing import Any, Iterator
from urllib.parse import urljoin, urlparse

import requests

Block = dict[str, Any]

URL_RE = re.compile(r"https?://[^\s<>\"'、。」）\]]+")
OG_RE = [
    re.compile(r'<meta[^>]+(?:property|name)=["\'](?:og:image(?::secure_url)?|twitter:image(?::src)?)["\'][^>]*?content=["\']([^"\']+)', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*?(?:property|name)=["\'](?:og:image|twitter:image)["\']', re.I),
]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TheBrief/1.0; +https://heechang-newsletter.vercel.app)"}
OPENVERSE = "https://api.openverse.org/v1/images/"

# When a headline finds nothing, a picture of the subject itself.
FALLBACK_QUERY = {
    "china": "China city skyline",
    "mandarin": "Chinese calligraphy",
    "japan": "Tokyo",
    "watch": "wristwatch",
    "stocks": "stock exchange",
    "fintech": "finance technology",
    "business": "business meeting",
    "startup": "startup office",
}


def _texts(blocks: list[Block]) -> Iterator[str]:
    for b in blocks:
        if b.get("text"):
            yield b["text"]
        for item in b.get("items") or []:
            yield item
        yield from _texts(b.get("children") or [])


def _source_urls(blocks: list[Block]) -> list[str]:
    urls: list[str] = []
    for text in _texts(blocks):
        for u in URL_RE.findall(text):
            if u not in urls:
                urls.append(u)
    return urls


def _og_image(page: str) -> str | None:
    try:
        resp = requests.get(page, headers=HEADERS, timeout=12, stream=True)
        if resp.status_code != 200 or "html" not in resp.headers.get("Content-Type", ""):
            return None
        head = resp.raw.read(400_000, decode_content=True).decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001 — a source that will not answer just has no cover
        return None
    for pattern in OG_RE:
        m = pattern.search(head)
        if m:
            url = urljoin(page, html.unescape(m.group(1)).strip())
            # Site logos and favicons are not covers.
            if url.startswith("http") and not re.search(r"\.svg(\?|$)|logo|favicon|default", url, re.I):
                return url
    return None


def _query(title: str) -> str:
    # The words that name the story: no tickers, brackets or punctuation runs.
    t = re.sub(r"\([^)]*\)|【[^】]*】|[\"“”'’:;,.!?—–|/]", " ", title)
    words = [w for w in t.split() if len(w) > 1][:6]
    return " ".join(words)


def _openverse(query: str, seed: str) -> dict[str, str] | None:
    try:
        resp = requests.get(OPENVERSE, headers=HEADERS, timeout=20, params={
            "q": query, "page_size": 12, "license_type": "commercial", "mature": "false",
        })
        results = [r for r in resp.json().get("results", []) if r.get("url")]
    except Exception:  # noqa: BLE001
        return None
    if not results:
        return None
    # The same headline words recur across issues; the slug picks among the
    # matches so neighbouring issues do not all wear the same photo.
    pick = results[int(hashlib.sha1(seed.encode()).hexdigest(), 16) % min(len(results), 6)]
    creator = pick.get("creator") or "unknown"
    license = (pick.get("license") or "").upper()
    return {
        "url": pick["url"],
        "credit": f"{creator} · CC {license}".strip(),
        "link": pick.get("foreign_landing_url") or pick["url"],
        "kind": "openverse",
    }


def find_cover(row: dict[str, Any]) -> dict[str, str] | None:
    """The cover for an issue row (needs blocks, title and section)."""
    blocks = row.get("blocks") or []
    for page in _source_urls(blocks)[:3]:
        image = _og_image(page)
        if image:
            host = urlparse(page).netloc.removeprefix("www.")
            return {"url": image, "credit": host, "link": page, "kind": "source"}
    seed = f"{row.get('section')}/{row.get('slug') or row.get('run_key') or row.get('title')}"
    query = _query(row.get("title") or "")
    return (query and _openverse(query, seed)) or _openverse(FALLBACK_QUERY.get(row.get("section", ""), "news"), seed)
