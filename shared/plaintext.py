"""Plain-text issue → Notion blocks.

The Japanese newsletters are written as plain text, because the same string has
to read correctly inside a Google Calendar event, where no markup renders. The
structure is carried by markers instead: ━━━ for a divider, SECTION … for a
section header, 【…】 for a story headline, 📖 for a callout.

Lifted out of japan-newsletter/main.py when a second newsletter needed the same
format, the way china-newsletter/blocks.py became shared/markers.py. The parser
never cared which newsletter it was reading.
"""

from __future__ import annotations

# Notion truncates a single rich-text run past this.
RICH_TEXT_LIMIT = 2000

# Standalone header lines. A SECTION prefix is matched separately, so this only
# has to name headers that stand on their own.
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

_KOREAN_MARKERS = (
    "📝 한국어 번역:",
    "📝 한국어 번역",
    "📝 한국어번역:",
    "📝 한국어번역",
)


def rich_text(content: str) -> dict:
    return {"type": "text", "text": {"content": content[:RICH_TEXT_LIMIT]}}


def is_divider(line: str) -> bool:
    return "━" in line and line.strip().count("━") >= 5


def is_section_header(line: str) -> bool:
    """Only lines that ARE section headers, not body text containing the words."""
    stripped = line.strip()
    if not stripped:
        return False
    upper = stripped.upper()
    if upper.startswith("SECTION "):
        return True
    return any(upper == h or stripped == h for h in _SECTION_HEADER_EXACT)


def to_notion_blocks(text: str) -> list[dict]:
    blocks: list[dict] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        if is_divider(stripped):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            continue

        if is_section_header(stripped):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [rich_text(stripped)], "is_toggleable": False},
            })
            continue

        # Only 【…】 lines short enough to be a headline, so a body paragraph
        # that happens to quote one does not become a heading.
        if stripped.startswith("【") and "】" in stripped and len(stripped) < 120:
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [rich_text(stripped)], "is_toggleable": False},
            })
            continue

        # The marker itself carries no content — the Korean follows as a plain
        # paragraph, which is what the furigana pass and the reader both expect.
        if stripped in _KOREAN_MARKERS:
            continue

        if stripped.startswith("📖"):
            blocks.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [rich_text(stripped[1:].strip())],
                    "icon": {"emoji": "📖"},
                },
            })
            continue

        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [rich_text(stripped)]},
        })
    return blocks
