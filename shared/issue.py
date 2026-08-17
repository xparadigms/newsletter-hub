"""Assembling the row an issue becomes in Supabase.

parse_title mirrors parseTitle in web/lib/notion-map.ts character for character.
It has to: the 318 migrated issues had their title and series split by the
TypeScript, and every issue from here on is split by this. A divergence would
show up as one section's tags rendering differently from the rest.
"""

from __future__ import annotations

import re
from typing import Any

from . import blocks as blocks_mod

# "[Series #N] (Headline)" or "[Series #N] Headline".
_BRACKET = re.compile(r"^\[([^\]]+)\]\s*([\s\S]*)$")
_WRAPPED = re.compile(r"^\(([\s\S]*)\)$")
_ISSUE_NO = re.compile(r"#\s*(\d+)")


def parse_title(raw: str) -> tuple[str, str | None, int | None]:
    """Split a raw issue title into (headline, series, issue number)."""
    m = _BRACKET.match(raw)
    if not m:
        return raw, None, None

    series = m.group(1).strip()
    rest = m.group(2).strip()
    wrapped = _WRAPPED.match(rest)
    if wrapped:
        rest = wrapped.group(1).strip()

    number = _ISSUE_NO.search(series)
    return (rest or raw), series, (int(number.group(1)) if number else None)


# Mirrors the database CHECK. Without it a typo costs the whole run: the write
# is the last step, so it fails after both Claude calls have been paid for.
SECTIONS = frozenset({"startup", "fintech", "japan", "watch", "china"})


def build_row_from_blocks(
    *,
    section: str,
    issue_date: str,
    raw_title: str,
    blocks: list[dict],
    source_text: str,
    source_format: str,
    summary: str | None = None,
) -> dict[str, Any]:
    """The row to upsert, given the website's Block[] directly.

    `slug` is deliberately absent — the database trigger derives it and keeps an
    existing one, so a same-day rerun republishes under the URL it first used.
    """
    if section not in SECTIONS:
        raise ValueError(f"unknown section {section!r}; expected one of {sorted(SECTIONS)}")

    title, series, issue_number = parse_title(raw_title)
    return {
        "section": section,
        "issue_date": issue_date,
        "title": title,
        "series": series,
        "raw_title": raw_title,
        "issue_number": issue_number,
        "summary": summary,
        "blocks": blocks,
        "plain_text": blocks_mod.plain_text(blocks),
        "source_text": source_text,
        "source_format": source_format,
        # One issue per section per day. A rerun replaces its own row rather
        # than adding a duplicate, independent of github.run_number.
        "run_key": f"{section}:{issue_date}",
        "published": True,
    }


def build_row(
    *,
    section: str,
    issue_date: str,
    raw_title: str,
    notion_blocks: list[dict],
    source_text: str,
    source_format: str,
    summary: str | None = None,
) -> dict[str, Any]:
    """The Notion-shaped path: the four mirroring generators hand over the
    blocks they are about to send Notion, and this maps them. China builds
    Block[] natively and calls build_row_from_blocks instead."""
    return build_row_from_blocks(
        section=section,
        issue_date=issue_date,
        raw_title=raw_title,
        blocks=blocks_mod.notion_blocks_to_web(
            blocks_mod.strip_expiring_images(notion_blocks)
        ),
        source_text=source_text,
        source_format=source_format,
        summary=summary,
    )
