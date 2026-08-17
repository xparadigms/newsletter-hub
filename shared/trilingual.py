"""Notion-flavoured Markdown → Notion blocks.

The parser behind the startup and watch newsletters, which generate their issues
as trilingual Markdown (headings, <details> furigana toggles, <callout>
translation blocks, dividers, bullet lists) rather than plain text.

Lifted unchanged from upload_trilingual_to_notion.py, which existed as two
verbatim 343-line forks in startup-newsletter/ and watch-newsletter/ differing
on exactly two lines: a default database id and a default page title. Both of
those belonged to the uploader half of that file, which is dropped here — each
generator's own create_notion_page() does the writing.

_md_to_blocks is exported without the underscore as md_to_blocks; the private
name is kept as an alias so the lifted body needs no edits.
"""

import re

# ── Rich-text helpers ────────────────────────────────────────────────────────

def _rt(content: str, bold: bool = False, italic: bool = False, code: bool = False) -> dict:
    """Build a single Notion rich-text segment."""
    obj: dict = {"type": "text", "text": {"content": content[:2000]}}
    annotations = {}
    if bold:
        annotations["bold"] = True
    if italic:
        annotations["italic"] = True
    if code:
        annotations["code"] = True
    if annotations:
        obj["annotations"] = annotations
    return obj


def _parse_inline(text: str) -> list[dict]:
    """Parse **bold** and *italic* runs inside a line into rich-text segments."""
    segments: list[dict] = []
    # Pattern: **bold** or *italic*
    pattern = re.compile(r"(\*\*(.+?)\*\*|\*(.+?)\*)")
    last = 0
    for m in pattern.finditer(text):
        if m.start() > last:
            segments.append(_rt(text[last : m.start()]))
        if m.group(2):  # **bold**
            segments.append(_rt(m.group(2), bold=True))
        elif m.group(3):  # *italic*
            segments.append(_rt(m.group(3), italic=True))
        last = m.end()
    if last < len(text):
        segments.append(_rt(text[last:]))
    return segments or [_rt(text)]


# ── Block builders ───────────────────────────────────────────────────────────

def _divider():
    return {"object": "block", "type": "divider", "divider": {}}


def _heading2(text: str, color: str = "default"):
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": _parse_inline(text), "color": color, "is_toggleable": False},
    }


def _heading3(text: str, color: str = "default"):
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {"rich_text": _parse_inline(text), "color": color, "is_toggleable": False},
    }


def _paragraph(text: str, color: str = "default"):
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _parse_inline(text), "color": color},
    }


def _bold_paragraph(text: str, color: str = "default"):
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [_rt(text, bold=True)], "color": color},
    }


def _bullet(text: str):
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _parse_inline(text)},
    }


def _toggle(summary_text: str, child_text: str):
    """A toggle heading_3 or paragraph with children — Notion uses toggle blocks."""
    return {
        "object": "block",
        "type": "toggle",
        "toggle": {
            "rich_text": [_rt(summary_text)],
            "children": [_paragraph(child_text.strip())],
        },
    }


def _callout(text: str, icon: str = "📝", color: str = "gray_background"):
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": _parse_inline(text),
            "icon": {"type": "emoji", "emoji": icon},
            "color": color,
        },
    }


# ── Markdown → Notion block parser ──────────────────────────────────────────

def _md_to_blocks(md_text: str) -> list[dict]:
    """Convert the trilingual newsletter Markdown into Notion API blocks."""
    lines = md_text.split("\n")
    blocks: list[dict] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            i += 1
            continue

        # --- Dividers ---
        if stripped == "---":
            blocks.append(_divider())
            i += 1
            continue

        # # H1 title
        if stripped.startswith("# ") and not stripped.startswith("## "):
            blocks.append(_heading2(stripped[2:], color="blue_background"))
            i += 1
            continue

        # ## H2
        if stripped.startswith("## "):
            blocks.append(_heading2(stripped[3:], color="blue_background"))
            i += 1
            continue

        # ### H3 (story headings with 【…】)
        if stripped.startswith("### "):
            blocks.append(_heading3(stripped[4:]))
            i += 1
            continue

        # <details> … </details> → toggle block
        if stripped == "<details>":
            # Collect summary and body
            summary = ""
            body_lines = []
            i += 1
            while i < len(lines):
                s = lines[i].strip()
                if s.startswith("<summary>"):
                    summary = re.sub(r"</?summary>", "", s).strip()
                elif s == "</details>":
                    i += 1
                    break
                else:
                    body_lines.append(lines[i].strip())
                i += 1
            body = "\n".join(body_lines).strip()
            blocks.append(_toggle(summary or "ふりがな（ひらがな）", body))
            continue

        # <callout icon="…"> … </callout>
        # The callout is normally just a "한국어 번역" label marker, with the
        # actual Korean translation following as a separate paragraph. But the
        # model frequently inlines the real translation *inside* the callout
        # instead — so collect the body, drop the label line, and render any
        # remaining content as a paragraph. This guarantees the Korean text is
        # never silently dropped while keeping the clean (label-free) layout.
        if stripped.startswith("<callout"):
            i += 1
            callout_lines: list[str] = []
            while i < len(lines):
                s = lines[i].strip()
                if s == "</callout>":
                    i += 1
                    break
                if s:
                    callout_lines.append(s)
                i += 1
            content = "\n".join(
                l for l in callout_lines if l != "한국어 번역"
            ).strip()
            if content:
                blocks.append(_paragraph(content))
            continue

        # ▸ Sub-section labels (What happened, Industry status, etc.)
        if stripped.startswith("▸ ") and len(stripped) < 40:
            blocks.append(_bold_paragraph(stripped))
            i += 1
            continue

        # 왜 중요한가: → callout
        if stripped.startswith("왜 중요한가:"):
            blocks.append(_callout(stripped, icon="💡", color="yellow_background"))
            i += 1
            continue

        # Bullet list items: - **text** or - text
        if stripped.startswith("- "):
            content = stripped[2:]
            blocks.append(_bullet(content))
            i += 1
            continue

        # Korean subtitle line in parentheses
        if stripped.startswith("(") and stripped.endswith(")"):
            blocks.append(_paragraph(stripped, color="gray"))
            i += 1
            continue

        # Italic line *English headline*
        if stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("**"):
            blocks.append(_paragraph(stripped))
            i += 1
            continue

        # Default → paragraph
        blocks.append(_paragraph(stripped))
        i += 1

    return blocks


# Public name; the module-internal callers above keep using the underscore.
md_to_blocks = _md_to_blocks
