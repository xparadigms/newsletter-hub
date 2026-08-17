"""Claude's marker-delimited issue → the website's Block[].

The contract is three line prefixes and nothing else:

    SUMMARY: <one Korean sentence for the front-page deck>
    MAIN_TITLE: <English title of the lead story>
    ### <Korean headline, unnumbered>
    <Chinese sentence line>            (one or more)
    > <Korean translation of them all>

`###` and `>` are used because Chinese prose never begins a line with either,
so no escaping is needed and a missed marker cannot be mistaken for content.

Headings are written unnumbered and the ordinal is added here: asking the model
to number its own stories invites skipped, repeated or restarted numbering, and
the number is what renders in gold.
"""

from __future__ import annotations

import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from shared import pinyin  # noqa: E402

# Tolerates a leading ordinal in case the model adds one anyway.
_HEADING = re.compile(r"^###\s+(?:\d{1,2}[.)]\s*)?(.*)$")
_TRANSLATION = re.compile(r"^>\s*(.*)$")


def parse_meta(issue_text: str) -> tuple[str, str | None]:
    """(main_title, summary) from the leading marker lines."""
    main_title = "China Daily"
    summary = None
    for line in issue_text.split("\n")[:8]:
        s = line.strip()
        if s.startswith("MAIN_TITLE:"):
            main_title = s[len("MAIN_TITLE:") :].strip() or main_title
        elif s.startswith("SUMMARY:"):
            summary = s[len("SUMMARY:") :].strip() or None
    return main_title, summary


def to_notion_blocks(blocks: list[dict]) -> list[dict]:
    """The website's Block[] → Notion blocks, for the browsable mirror.

    Notion has no per-word ruby, so a `pinyin` block becomes the Chinese
    sentence as a paragraph followed by a 拼音 toggle holding the readings —
    the same shape the Japanese newsletters use for furigana, so the two read
    consistently in Notion. The readings are joined in reading order, which is
    what you want when checking a word rather than reading the line.
    """
    out: list[dict] = []

    def rich(text: str) -> list[dict]:
        return [{"type": "text", "text": {"content": text[:2000]}}]

    for b in blocks:
        kind = b["type"]
        if kind == "heading":
            out.append(
                {"type": "heading_3", "heading_3": {"rich_text": rich(b["text"])}}
            )
        elif kind == "pinyin":
            sentence = "".join(w["text"] for w in b["words"])
            reading = " ".join(w["pinyin"] for w in b["words"] if w.get("pinyin"))
            out.append({"type": "paragraph", "paragraph": {"rich_text": rich(sentence)}})
            if reading:
                out.append(
                    {
                        "type": "toggle",
                        "toggle": {
                            "rich_text": rich("拼音"),
                            "children": [
                                {
                                    "type": "paragraph",
                                    "paragraph": {"rich_text": rich(reading)},
                                }
                            ],
                        },
                    }
                )
        elif kind == "quote":
            # The Korean read-through, in the callout the other newsletters use
            # for translations so it reads the same in Notion.
            out.append(
                {
                    "type": "callout",
                    "callout": {
                        "rich_text": rich(b["text"]),
                        "icon": {"emoji": "📝"},
                    },
                }
            )
        elif kind == "paragraph":
            out.append({"type": "paragraph", "paragraph": {"rich_text": rich(b["text"])}})
        elif kind == "divider":
            out.append({"type": "divider", "divider": {}})
    return out


def build_blocks(issue_text: str) -> tuple[list[dict], int, int]:
    """Return (blocks, story_count, unsegmented_line_count)."""
    blocks: list[dict] = []
    stories = 0
    unsegmented = 0

    for raw in issue_text.split("\n"):
        line = raw.strip()
        if not line or line.startswith(("SUMMARY:", "MAIN_TITLE:")):
            continue

        heading = _HEADING.match(line)
        if heading:
            stories += 1
            # level 2 renders as <h3>. Level 1 would be an <h2> section banner,
            # and buildDeck turns a level<=2 group with no body into a divider
            # card — every china group has a body, so none appear.
            blocks.append(
                {"type": "heading", "level": 2, "text": f"{stories}. {heading.group(1).strip()}"}
            )
            continue

        translation = _TRANSLATION.match(line)
        if translation:
            blocks.append({"type": "quote", "text": translation.group(1).strip()})
            continue

        words = pinyin.annotate(line)
        if pinyin.check_lossless(line, words):
            blocks.append({"type": "pinyin", "words": words})
        else:
            # Segmentation that loses characters would silently drop half a
            # sentence. Keep the text as a plain paragraph instead — no
            # readings, but nothing lost — and let the caller decide whether
            # the failure rate is bad enough to abort.
            unsegmented += 1
            blocks.append({"type": "paragraph", "text": line})

    return blocks, stories, unsegmented
