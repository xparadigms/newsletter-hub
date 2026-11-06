"""One issue, published as one article per story.

Startup, Business Insight, Rails and China Daily are still written as a single
issue — the prompts, the Notion page and the calendar event are unchanged — and
split only at the end, at the headings that start each story. Each story becomes
its own row, titled by its own headline and tagged "[Series #N · 2/4]", the way
Three Companies publishes one article per company.

What sits before the first story (issue banners, a preview of all of them) is
dropped: it introduces the issue, not any one article. What follows the last
story is either its own closing article (Rails' Food for Thought) or, for a
section with no closing title (Startup's 今週の表現), folded into the last
story. A part too short to pass the refusal guard in shared/issue.py is folded
into the one before it rather than failing the run, so a thin day still
publishes.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from . import audio, blocks as blocks_mod, issue as issue_row, store

Block = dict[str, Any]
Predicate = Callable[[Block], bool]


def _trim(part: list[Block]) -> list[Block]:
    """Without leading or trailing dividers, which only separated stories."""
    start, end = 0, len(part)
    while start < end and part[start].get("type") == "divider":
        start += 1
    while end > start and part[end - 1].get("type") == "divider":
        end -= 1
    return part[start:end]


def split_parts(
    blocks: list[Block],
    *,
    starts: Predicate,
    tail: Predicate | None = None,
    skip: Predicate | None = None,
) -> tuple[list[list[Block]], list[Block]]:
    """(stories, tail) from the website's Block[].

    `starts` marks the block that opens a story, `tail` the block that opens
    the closing matter after the last story, and `skip` blocks to drop anywhere,
    such as "SECTION 2" banners that only numbered the stories inside one page.
    """
    stories: list[list[Block]] = []
    closing: list[Block] = []
    in_tail = False
    for b in blocks:
        if skip and skip(b):
            continue
        if in_tail:
            closing.append(b)
        elif stories and tail and tail(b):
            in_tail = True
            closing.append(b)
        elif starts(b):
            stories.append([b])
        elif stories:
            stories[-1].append(b)
        # else: front matter, dropped
    return [_trim(s) for s in stories if _trim(s)], _trim(closing)


# The shortest article a section may publish, where the issue-wide refusal
# guard does not fit. A China Daily story is one card by design — a heading,
# two Chinese sentences and their Korean, about 150 characters — so the 700
# that catches a refusal would fold all four stories back into one article.
# China's refusal guard is structural instead: main.py stops when the model
# wrote no ### stories, and this floor only catches a story left empty.
PART_MIN_CHARS = {"china": 40}


def _min_chars(section: str) -> int:
    return PART_MIN_CHARS.get(section, issue_row.MIN_PLAIN_TEXT)


def _long_enough(part: list[Block], min_chars: int = issue_row.MIN_PLAIN_TEXT) -> bool:
    return len(blocks_mod.plain_text(part)) >= min_chars


def merge_parts(
    section: str,
    stories: list[tuple[str, list[Block]]],
    closing: tuple[str | None, list[Block]] | None,
) -> list[tuple[str, list[Block]]]:
    """The (title, blocks) articles an issue is published as, first first.

    A closing with a title is its own last article when it is long enough to
    stand alone; a closing titled None always joins the last story. Pure, so
    china-newsletter/rerender.py can rebuild exactly the part a stored row
    holds without storing anything.
    """
    min_chars = _min_chars(section)
    parts = [(t, b) for t, b in stories if b]
    if closing and closing[1]:
        title, body = closing
        if parts and (title is None or not _long_enough(body, min_chars)):
            parts[-1] = (parts[-1][0], parts[-1][1] + body)
        elif title is not None:
            parts.append((title, body))
    # Fold a story too short to stand alone into the one before it.
    merged: list[tuple[str, list[Block]]] = []
    for title, part in parts:
        if merged and not _long_enough(part, min_chars):
            merged[-1] = (merged[-1][0], merged[-1][1] + part)
        else:
            merged.append((title, part))
    # A short first story has nothing before it, so it joins the next one.
    if len(merged) > 1 and not _long_enough(merged[0][1], min_chars):
        merged[1] = (merged[0][0], merged[0][1] + merged[1][1])
        merged.pop(0)
    return merged


def publish(
    *,
    section: str,
    issue_date: str,
    series: str,
    stories: list[tuple[str, list[Block]]],
    closing: tuple[str | None, list[Block]] | None,
    source_text: str,
    source_format: str,
    edition: int,
    fallback: tuple[str, list[Block]],
    audio_lang: str | None = "ja",
) -> list[dict[str, Any]]:
    """Store each story as its own article and return the stored rows, first
    article first.

    `stories` and `closing` are (title, blocks); a closing titled None joins
    the last story (see merge_parts). With no stories found the issue is
    stored whole under `fallback` (raw title, blocks), exactly as it was
    before splitting existed, so a format change can never cost a day.

    Every row carries the whole issue's source_text: it is what the next runs
    read to avoid repeating a story (sources.already_covered), and store.
    recent_issues returns every part of the recent issues together.
    """
    merged = merge_parts(section, stories, closing)

    if not merged:
        raw_title, whole = fallback
        rows = [
            issue_row.build_row_from_blocks(
                section=section,
                issue_date=issue_date,
                raw_title=raw_title,
                blocks=whole,
                source_text=source_text,
                source_format=source_format,
                edition=edition,
            )
        ]
    else:
        n = len(merged)
        rows = [
            issue_row.build_row_from_blocks(
                section=section,
                issue_date=issue_date,
                raw_title=f"[{series} · {i}/{n}] ({title})",
                blocks=part,
                source_text=source_text,
                source_format=source_format,
                edition=edition,
                part=i,
                min_plain_text=_min_chars(section),
            )
            for i, (title, part) in enumerate(merged, start=1)
        ]

    for row in rows:
        if audio_lang:
            try:
                print(f"  ✓ Audio {row['title'][:40]}: {audio.attach_audio(row['blocks'], audio_lang)} block(s)")
            except Exception as e:  # noqa: BLE001 — a silent article still publishes
                print(f"  ⚠ Audio failed (non-fatal): {e}")

    # Last to first: a day's list is ordered by published_at, newest on top,
    # so storing part 1 last puts it first.
    stored: list[dict[str, Any]] = []
    for row in reversed(rows):
        result = store.upsert_issue(row)
        stored.insert(0, {**row, **result})
        if result.get("slug"):
            print(f"✓ Stored: {section}/{result['slug']}")
            store.ping_revalidate(section, result["slug"])
    return stored


# ── Where each newsletter's stories start ──────────────────────────────────
def _heading(level: int, test: Callable[[str], bool] = lambda t: True) -> Predicate:
    return lambda b: (
        b.get("type") == "heading" and b.get("level") == level and test(b.get("text") or "")
    )


# Shared by the generators and by resplit.py, so an issue split after the fact
# comes out exactly as one split at publishing time.
RULES: dict[str, dict[str, Predicate]] = {
    # 【Japanese headline】 per story; 今週の表現 is the level-2 heading after
    # them. In issues from before Other Notable Headlines was dropped, that
    # heading comes first and opens the tail the same way.
    "startup": {"starts": _heading(3, lambda t: t.startswith("【")), "tail": _heading(2)},
    # "1. Headline" per Deep Read; FOOD FOR THOUGHT is the level-2 heading
    # after them (THE SWEEP was, in issues from before it was dropped).
    "fintech": {
        "starts": _heading(3, lambda t: bool(re.match(r"^\d+\.\s", t))),
        "tail": _heading(2),
    },
    # 【Japanese insight】 per insight; "SECTION N" banners dropped.
    "business": {
        "starts": _heading(3, lambda t: t.startswith("【")),
        "skip": _heading(2, lambda t: t.upper().startswith("SECTION")),
    },
    # "1. Korean headline" per story. These are the only headings
    # shared/markers.py writes, so nothing comes before the first story and
    # nothing after the last.
    "china": {"starts": _heading(2)},
}

# The title a section's closing matter is published under as its own article.
# Startup has none: with Other Notable Headlines gone its closing is only
# 今週の表現, which is not a story, so it rides along with the last story.
CLOSING_TITLES = {"fintech": "Food for Thought"}

_CJK = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7a3]")


def story_title(section: str, story: list[Block]) -> str:
    """The headline a story is published under, in English where there is one.

    Startup writes its English headline as the first English paragraph under
    the 【Japanese】 heading; Rails' heading is English after its number, and
    China Daily's is Korean after its number. Business has no English headline
    in the body, so its generator asks for one per insight and this is only
    the fallback: the Japanese headline.
    """
    head = (story[0].get("text") or "").strip()
    if section == "startup":
        for b in story[1:6]:
            text = (b.get("text") or "").strip()
            if (
                b.get("type") == "paragraph"
                and text
                and not _CJK.search(text)
                and not text.startswith(("▸", "(", "🔗"))
            ):
                return text
    if section in ("fintech", "china"):
        return re.sub(r"^\d+\.\s+", "", head)
    return head.split("】")[0].strip("【 ")


def to_web(notion_blocks: list[Block]) -> list[Block]:
    """The website's Block[] from Notion-shaped blocks, as build_row does it."""
    return blocks_mod.notion_blocks_to_web(blocks_mod.strip_expiring_images(notion_blocks))
