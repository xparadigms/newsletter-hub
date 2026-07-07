#!/usr/bin/env python3
"""Upload a trilingual newsletter Markdown file to Notion with rich formatting.

Converts Notion-flavoured Markdown (headings, <details> toggles, <callout> blocks,
dividers, bullet lists) into the Notion block API format and creates a page in the
configured newsletter database.

Usage:
    python upload_trilingual_to_notion.py [path_to_md]

If no path is given, defaults to the most recent test_output_*.md in the script dir.
"""

import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

import requests

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.environ.get(
    "NOTION_DATABASE_ID", "3965bc953df381bbb5ece93744153a6a"
)
NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"
KST = timezone(timedelta(hours=9))


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


# ── Notion upload ────────────────────────────────────────────────────────────

def upload_to_notion(md_text: str, title: Optional[str] = None) -> str:
    """Create a Notion page from trilingual Markdown. Returns the page URL."""
    if not NOTION_TOKEN:
        print("  ⚠ NOTION_TOKEN not set. Cannot upload.")
        return ""

    now_kst = datetime.now(KST)
    date_str = now_kst.strftime("%Y-%m-%d")

    if not title:
        title = f"⌚ Watch Weekly (Trilingual) — {now_kst.strftime('%b %d, %Y')}"

    all_blocks = _md_to_blocks(md_text)
    print(f"  Parsed {len(all_blocks)} Notion blocks.")

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": date_str}},
        },
        "children": all_blocks[:100],
    }

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    resp = requests.post(NOTION_API_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    page = resp.json()
    page_id = page["id"]

    # Append remaining blocks in batches of 100
    for batch_start in range(100, len(all_blocks), 100):
        batch = all_blocks[batch_start : batch_start + 100]
        append_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        r = requests.patch(
            append_url, headers=headers, json={"children": batch}, timeout=60
        )
        r.raise_for_status()
        print(f"  Appended blocks {batch_start}–{batch_start + len(batch)}.")

    return page.get("url", "")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    script_dir = Path(__file__).resolve().parent

    if len(sys.argv) > 1:
        md_path = Path(sys.argv[1])
    else:
        # Find the most recent test_output_*.md
        candidates = sorted(script_dir.glob("test_output_*.md"), reverse=True)
        if not candidates:
            print("✗ No test_output_*.md file found. Pass a path as argument.")
            sys.exit(1)
        md_path = candidates[0]

    print(f"▸ Reading {md_path.name}...")
    md_text = md_path.read_text(encoding="utf-8")

    print("▸ Uploading to Notion...")
    url = upload_to_notion(md_text)
    if url:
        print(f"✓ Notion page created: {url}")
    else:
        print("✗ Upload failed or NOTION_TOKEN not set.")


if __name__ == "__main__":
    main()
