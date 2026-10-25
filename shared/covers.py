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
import os
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

# When the headline finds nothing, a picture of the subject itself — and never
# of people: a stranger's face beside a story about a named person reads as
# that person.
FALLBACK_QUERY = {
    "china": ["Shanghai skyline", "Beijing city", "Chinese architecture"],
    "mandarin": ["Chinese calligraphy", "Chinese characters", "Chinese lanterns"],
    "japan": ["Tokyo skyline", "Japanese street", "Shibuya crossing"],
    "watch": ["wristwatch", "watch dial", "chronograph"],
    "stocks": ["stock market chart", "stock ticker board", "trading screen"],
    "fintech": ["credit card payment", "digital payment", "bank building"],
    "business": ["office building", "city skyline night", "modern architecture"],
    "startup": ["laptop desk", "circuit board", "server room"],
}

STOPWORDS = set("""a an the and or of for to in on at by with from as is are was were be been its it this that
these those into over after before about than then via amid new says say how why what when who will can could
may might more most less least first last just even still now also not no yes up down out off all any each
""".split())

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


QUERY_MODEL = "claude-haiku-5-5"

QUERY_PROMPT = """Headline: {title}
Newsletter: {section}

Give three searches for a stock photo to illustrate this headline, most specific
first. Each is one to three plain English words naming something a photograph
can show: an object, a place, a product, a building or a company's logo — for
example "stablecoin", "Tokyo skyline", "Nvidia chip", "container port". Never a
person's name or a face. One search per line, nothing else."""


def _llm_queries(title: str, section: str) -> list[str]:
    """Searches chosen by a small model, which reads a headline the way a
    picture editor would. Empty if no model is available."""
    if not (os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")):
        return []
    try:
        from . import llm

        text = llm.complete(model=QUERY_MODEL, system="You pick photo searches.", label="cover search",
                            user=QUERY_PROMPT.format(title=title, section=section), max_tokens=60)
    except Exception as e:  # noqa: BLE001 — the word-based searches still run
        print(f"  ⚠ cover search model failed: {e}")
        return []
    lines = [re.sub(r"^[\s\d.)\-*\"']+|[\"'.]+$", "", l).strip() for l in text.splitlines()]
    return [l for l in lines if 0 < len(l) <= 40][:3]


def _queries(title: str) -> list[str]:
    """Searches to try, most specific first. Openverse matches every word, so a
    whole headline finds nothing; two or three of its key words usually do."""
    t = title
    # "Horowitz: Exceptional strength…" — the part before the colon is a
    # speaker, and searching a name returns photos of other people.
    m = re.match(r"^([A-Z][\w.'’-]+(?: [A-Z][\w.'’-]+)?):\s+(.+)$", t)
    if m:
        t = m.group(2)
    t = re.sub(r"\([^)]*\)|【[^】]*】|\d[\d.,%$]*[A-Za-z]*", " ", t)
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]+", t) if w.lower() not in STOPWORDS and len(w) > 2]
    out: list[str] = []
    for n in (3, 2):
        if len(words) >= n:
            out.append(" ".join(words[:n]))
    if words:
        out.append(max(words, key=len))
    return out


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
    title = row.get("title") or ""
    for query in _llm_queries(title, row.get("section", "")) + _queries(title):
        cover = _openverse(query, seed)
        if cover:
            return {**cover, "query": query}
    fallbacks = FALLBACK_QUERY.get(row.get("section", ""), ["city skyline"])
    pick = fallbacks[int(hashlib.sha1(seed.encode()).hexdigest(), 16) % len(fallbacks)]
    cover = _openverse(pick, seed)
    return {**cover, "query": pick} if cover else None
