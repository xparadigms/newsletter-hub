#!/usr/bin/env python3
"""Podcast Hub — one article per new podcast episode, in Japanese and Korean.

Every few hours this reads the shows' RSS feeds, and each episode it has not
written up yet becomes its own article: what was argued, the three or four
ideas worth keeping, and how to use them. It uses the same Japanese business
register with a full Korean translation under every paragraph as Business
Insight, so a summary of All-In doubles as reading practice.

The material behind a summary is what the episode itself publishes: the show
notes, and the full transcript when the feed carries one (Lenny's Podcast
does). Notes alone are often a paragraph of sponsor reads, so for an episode
without a transcript the writer first searches the web for coverage of it —
a YouTube description, a write-up, the guest's own post.

An episode is identified by its feed GUID, and its run_key carries the
episode's own date, so a run that sees the same episode again replaces
nothing and writes nothing: `_already_written` asks Supabase first.
"""

from __future__ import annotations

import hashlib
import html
import os
import pathlib
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from shared import audio, furigana, http, issue, llm, plaintext, split, store  # noqa: E402

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
KST = timezone(timedelta(hours=9))
SECTION = "podcasts"

MODEL = "claude-sonnet-4-6"
# Through Claude Code, Sonnet 4.6 cannot hold a multi-turn search session.
RESEARCH_MODEL = "claude-sonnet-5"
MAX_TOKENS = 12000

# Episodes older than this are never written up, so a new show added to the
# list does not publish its back catalogue.
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "4"))
# Per run. Each episode costs a search session and two model calls, and a run
# every few hours catches up within the day.
MAX_EPISODES = int(os.environ.get("MAX_EPISODES", "4"))
# Rewrite episodes already published (same run_key, so the same URL) instead
# of skipping them — for a change of format. The workflow sends no
# notifications for a rewrite.
REWRITE = os.environ.get("REWRITE", "") == "true"

# slug: the run_key part and the filter's key; it must never change once used.
SHOWS: list[dict[str, str]] = [
    {"slug": "allin", "name": "All-In", "feed": "https://allinchamathjason.libsyn.com/rss"},
    {"slug": "mastersofscale", "name": "Masters of Scale", "feed": "https://rss.art19.com/masters-of-scale"},
    {"slug": "lenny", "name": "Lenny's Podcast", "feed": "https://api.substack.com/feed/podcast/10845.rss"},
    {"slug": "iltb", "name": "Invest Like the Best", "feed": "https://feeds.megaphone.fm/investlikethebest"},
    {"slug": "20vc", "name": "20VC", "feed": "https://thetwentyminutevc.libsyn.com/rss"},
    {"slug": "acquired", "name": "Acquired", "feed": "https://feeds.transistor.fm/acquired"},
    {"slug": "mfm", "name": "My First Million", "feed": "https://feeds.megaphone.fm/HS2300184645"},
    {"slug": "a16z", "name": "a16z Podcast", "feed": "https://feeds.simplecast.com/JGE3yC0V"},
    {"slug": "bg2", "name": "BG2Pod", "feed": "https://anchor.fm/s/f06c2370/podcast/rss"},
    {"slug": "decoder", "name": "Decoder", "feed": "https://feeds.megaphone.fm/recodedecode"},
    {"slug": "hibt", "name": "How I Built This", "feed": "https://rss.art19.com/how-i-built-this"},
    {"slug": "hardfork", "name": "Hard Fork", "feed": "https://feeds.simplecast.com/l2i9YnTd"},
    {"slug": "tim", "name": "The Tim Ferriss Show", "feed": "https://rss.art19.com/tim-ferriss-show"},
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TheBrief/1.0; +https://heechang-newsletter.vercel.app)"}
BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
}
NOTES_CHARS = 8000
TRANSCRIPT_CHARS = 90000


# ── Feeds ───────────────────────────────────────────────────────────────────
def _text(raw: str) -> str:
    """Show notes as plain text: tags gone, links kept as bare URLs."""
    raw = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"\2 (\1)", raw, flags=re.S | re.I)
    raw = re.sub(r"<br\s*/?>|</p>|</li>", "\n", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html.unescape(raw)
    return re.sub(r"\n\s*\n+", "\n", raw).strip()


def _transcript(entry: Any) -> str:
    """The episode's podcast:transcript as plain text, or "" when it has none."""
    ref = entry.get("podcast_transcript")
    url = ref.get("url") if isinstance(ref, dict) else None
    if not url:
        return ""
    try:
        resp = requests.get(url, headers=BROWSER, timeout=30)
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ transcript unavailable: {e}")
        return ""
    lines = []
    for line in resp.text.splitlines():
        line = line.strip()
        # WebVTT and SRT: drop the header, cue numbers and timings.
        if not line or line == "WEBVTT" or line.isdigit() or "-->" in line:
            continue
        lines.append(_text(line))
    return " ".join(lines)[:TRANSCRIPT_CHARS]


def _published(entry: Any) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = entry.get(attr)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc).astimezone(KST)
    return None


def _episode_id(show: dict[str, str], entry: Any) -> str:
    key = entry.get("id") or entry.get("link") or entry.get("title") or ""
    return f"{show['slug']}-{hashlib.sha1(key.encode()).hexdigest()[:8]}"


def episodes(cutoff: datetime) -> list[dict[str, Any]]:
    """Every recent full episode across the shows, newest first."""
    found: list[dict[str, Any]] = []
    for show in SHOWS:
        try:
            # Fetched as a browser would: Substack answers a feed reader on a
            # datacenter address with 403.
            resp = requests.get(show["feed"], headers=BROWSER, timeout=30)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ {show['name']}: {e}")
            continue
        if not feed.entries:
            print(f"  ⚠ {show['name']}: no entries")
            continue
        show_image = (feed.feed.get("image") or {}).get("href")
        for entry in feed.entries[:10]:
            when = _published(entry)
            if not when or when < cutoff:
                continue
            if (entry.get("itunes_episodetype") or "full") != "full":
                continue  # trailers and bonus clips
            notes = max(
                [_text(c.value) for c in entry.get("content") or []] + [_text(entry.get("summary", ""))],
                key=len,
            )
            found.append({
                "show": show,
                "id": _episode_id(show, entry),
                "title": entry.get("title", "").strip(),
                "date": when,
                "link": entry.get("link") or "",
                "image": (entry.get("image") or {}).get("href") or show_image,
                "notes": notes[:NOTES_CHARS],
                "entry": entry,
            })
    found.sort(key=lambda e: e["date"], reverse=True)
    return found


def _run_key(ep: dict[str, Any]) -> str:
    return f"{SECTION}:{ep['date'].strftime('%Y-%m-%d')}:p{ep['id']}"


def _already_written(eps: list[dict[str, Any]]) -> set[str]:
    if not eps or not store.configured():
        return set()
    base, key = store._config()
    keys = ",".join(f'"{_run_key(e)}"' for e in eps)
    resp = http.request_with_retry(
        "GET", f"{base}/rest/v1/{store.TABLE}", label="Supabase", headers=store._headers(key),
        params={"select": "run_key", "run_key": f"in.({keys})"},
    )
    resp.raise_for_status()
    return {r["run_key"] for r in resp.json()}


def pick(eps: list[dict[str, Any]], done: set[str], limit: int) -> list[dict[str, Any]]:
    """The newest unwritten episodes, one per show before any show gets two."""
    todo = [e for e in eps if _run_key(e) not in done]
    chosen: list[dict[str, Any]] = []
    seen: set[str] = set()
    for e in todo:
        if e["show"]["slug"] not in seen and len(chosen) < limit:
            chosen.append(e)
            seen.add(e["show"]["slug"])
    for e in todo:
        if e not in chosen and len(chosen) < limit:
            chosen.append(e)
    return chosen


# ── Writing ─────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are the writer of "Podcast Hub", which turns each new episode of the \
podcasts founders and investors listen to — All-In, Masters of Scale, Lenny's \
Podcast, Acquired, 20VC — into a short Japanese article for a reader who runs \
a company and reads Japanese at roughly N3-N2. He did not listen to the \
episode; after reading he should know what was argued and what is worth \
keeping.

FAITHFULNESS IS NOT OPTIONAL. Write only what the material shows was said in \
this episode, and attribute each point to whoever made it. Never invent a \
quote, a number or an opinion; if the material only paraphrases, paraphrase. \
If the material is thin, write fewer points rather than padding.

Japanese: natural business Japanese, 敬体 (です・ます). Real vocabulary — 意思決定, \
資本効率, 参入障壁 — not textbook-simplified, not stiff translationese.

Korean register: 평어체. Every Korean sentence ends in the plain declarative \
form — ~다 / ~이다 / ~했다 / ~한다. Never 존댓말 (~습니다, ~합니다, ~예요, ~해요) \
and never 반말 endings (~야, ~지, ~거든).

CRITICAL TRANSLATION RULE: the Korean under each Japanese paragraph is a FULL \
translation — the same number of sentences, in the same order, with every \
name, number and qualifier carried across.

PARAGRAPH RULE: no paragraph, Japanese or Korean, exceeds 2 sentences. Each \
Japanese paragraph and its Korean are read together on one story card.

HEADING TRANSLATION RULE: every 【…】 heading is followed by its Korean \
translation in parentheses.

Names of people, companies and shows stay in their usual Latin spelling, or \
the standard katakana for well-known people.\
"""

EPISODE_PROMPT = """\
Write the Podcast Hub article for this episode.

Show: {show}
Episode: {title}
Published: {date}
Link: {link}

The first two lines MUST be:
EPISODE_TITLE: [an English title for the article, ≤10 words, naming the main idea — not the episode's own title]
SUMMARY_KO: [one short Korean sentence, 평어체, under 50 characters: what the episode is about]

Then exactly this format, as plain text:

【Japanese headline naming the episode's main idea】(Korean translation)
📖 番組: {show} · 出演: [the hosts and guests named in the material] · 配信: {date_ja}

[Japanese: what the episode is about, in ONE sentence of at most 60 characters.]
📝 한국어 번역:
[full Korean translation]

Then exactly THREE key points, the ideas worth keeping, each:

【ポイント{{N}}: short Japanese headline of the point】(Korean translation)

[Japanese: who said it and the substance — a number, an example or the reason \
— in at most 2 short sentences, 90 characters in all.]
📝 한국어 번역:
[full Korean translation]

Close with:

【どう使うか】(어떻게 쓸까)

[Japanese: one concrete thing someone running a company could do with this \
this week. ONE sentence, at most 60 characters; address the reader as あなた \
or write impersonally.]
📝 한국어 번역:
[full Korean translation]

LENGTH: short. The whole article is read in under a minute — five Japanese \
paragraphs, each under its character budget. Cut adjectives and background, \
never the names and numbers. The Korean is still a full translation.

⚠️ FORMATTING: plain text. No Markdown at all (no #, **, *, -, ```), no URLs, \
no emoji other than 📖 and 📝, and nothing before EPISODE_TITLE or after the \
last Korean paragraph.

--- MATERIAL ---
{material}
"""

RESEARCH_NOTE = """

The show notes above may be thin. Before writing, search the web for this \
specific episode — its YouTube description, a transcript, a write-up, or the \
guest's own post about it — and use what you find about what was actually \
said. Use only sources about this episode. Then reply with the article alone, \
in the format above.
"""


def _material(ep: dict[str, Any]) -> tuple[str, bool]:
    transcript = _transcript(ep["entry"])
    parts = [f"SHOW NOTES:\n{ep['notes'] or '(none)'}"]
    if transcript:
        parts.append(f"TRANSCRIPT:\n{transcript}")
    return "\n\n".join(parts), bool(transcript)


def write(ep: dict[str, Any]) -> str:
    material, has_transcript = _material(ep)
    prompt = EPISODE_PROMPT.format(
        show=ep["show"]["name"],
        title=ep["title"],
        date=ep["date"].strftime("%B %d, %Y"),
        date_ja=f"{ep['date'].year}年{ep['date'].month}月{ep['date'].day}日",
        link=ep["link"],
        material=material,
    )
    print(f"  material: {len(ep['notes'])} chars of notes" + (", a transcript" if has_transcript else ""))
    if not has_transcript and os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        try:
            text, urls, usage = llm.claude_code_search(
                RESEARCH_MODEL, SYSTEM_PROMPT, prompt + RESEARCH_NOTE, max_turns=12, timeout=900
            )
            print(usage.line("research+write") + f" · {len(urls)} URLs")
            if "EPISODE_TITLE:" in text and "【" in text:
                return text[text.index("EPISODE_TITLE:"):].strip()
            print("  ⚠ research reply was not an article; writing from the notes")
        except llm.ClaudeCodeError as e:
            print(f"  ⚠ research failed, writing from the notes: {e}")
    return llm.complete(
        model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM_PROMPT, user=prompt, label="write"
    ).strip()


def parse(text: str) -> tuple[str, str, str]:
    """(English title, Korean summary, article body) from the model's reply."""
    title, summary, body = "", "", []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("EPISODE_TITLE:") and not title:
            title = s.split(":", 1)[1].strip()
        elif s.startswith("SUMMARY_KO:") and not summary:
            summary = s.split(":", 1)[1].strip()
        else:
            body.append(line)
    text = "\n".join(body).strip()
    # Markdown slips through now and then; the reader shows it literally.
    text = re.sub(r"^\s*#+\s*|\*\*", "", text, flags=re.M)
    return title, summary, text


# ── Main ────────────────────────────────────────────────────────────────────
def publish(ep: dict[str, Any], dry_run: bool) -> None:
    show = ep["show"]
    print(f"▸ {show['name']} — {ep['title']} ({ep['date']:%Y-%m-%d})")
    title, summary, body = parse(write(ep))
    if not title or "【" not in body:
        raise RuntimeError(f"the reply was not an article: {body[:300]!r}")
    if ep["link"]:
        body += f"\n\n🔗 {ep['link']}"
    print(f"  Title: {title}")

    if dry_run:
        print("\n" + "=" * 60 + f"\n{summary}\n\n{body}\n" + "=" * 60)
        return

    blocks = plaintext.to_notion_blocks(body)
    try:
        blocks = furigana.augment(blocks, variant="sections", api_key=ANTHROPIC_API_KEY, group_by_story=True)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ Furigana failed (non-fatal): {e}")

    row = issue.build_row_from_blocks(
        section=SECTION,
        issue_date=ep["date"].strftime("%Y-%m-%d"),
        raw_title=f"[{show['name']}] ({title})",
        blocks=split.to_web(blocks),
        source_text=f"{show['name']}: {ep['title']}\n{ep['link']}\n\n{body}",
        source_format="plain",
        summary=summary or None,
        part=ep["id"],
        min_plain_text=300,
    )
    # The episode's own artwork, as the podcast app shows it.
    if ep["image"]:
        row["cover"] = {"url": ep["image"], "credit": show["name"], "link": ep["link"] or show["feed"], "kind": "source"}
    try:
        print(f"  ✓ Audio: {audio.attach_audio(row['blocks'], 'ja')} block(s)")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ Audio failed (non-fatal): {e}")
    result = store.upsert_issue(row)
    if result.get("slug"):
        print(f"✓ Stored: {SECTION}/{result['slug']}")
        store.ping_revalidate(SECTION, result["slug"])


def run() -> None:
    dry_run = "--dry-run" in sys.argv
    only = os.environ.get("SHOW", "").strip()
    cutoff = datetime.now(KST) - timedelta(days=LOOKBACK_DAYS)
    print(f"▸ Podcast Hub — episodes since {cutoff:%Y-%m-%d %H:%M} KST")

    eps = episodes(cutoff)
    if only:
        eps = [e for e in eps if e["show"]["slug"] == only]
    print(f"  {len(eps)} recent episode(s) across {len({e['show']['slug'] for e in eps})} show(s)")
    done = set() if REWRITE else _already_written(eps)
    if REWRITE:
        written = _already_written(eps)
        eps = [e for e in eps if _run_key(e) in written]
    chosen = pick(eps, done, MAX_EPISODES)
    if not chosen:
        print("  Nothing new to write.")
        return

    failures = 0
    for ep in chosen:
        try:
            publish(ep, dry_run)
        except Exception as e:  # noqa: BLE001 — one bad episode must not cost the rest
            failures += 1
            print(f"  ✗ {ep['show']['name']}: {e}")
    if failures == len(chosen):
        sys.exit(1)


if __name__ == "__main__":
    run()
