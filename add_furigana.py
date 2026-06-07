#!/usr/bin/env python3
"""Add furigana toggle blocks to the latest Japan Briefing Notion page.

For every Japanese body paragraph, inserts a collapsible toggle directly
below it (and above the 📝 한국어 번역 callout) containing a furigana-
annotated version of that paragraph.
"""

import json
import os
import sys
import time

import anthropic
import requests

# ── Config ──────────────────────────────────────────────────────────────────
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "36a5bc953df38036acb4d2b6553e582c")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

RATE_LIMIT_DELAY = 0.35  # seconds between Notion API writes


# ── Notion helpers ──────────────────────────────────────────────────────────
def find_latest_page() -> str:
    """Query the database for the most recent page and return its ID."""
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    payload = {
        "sorts": [{"property": "Date", "direction": "descending"}],
        "page_size": 1,
    }
    r = requests.post(url, headers=NOTION_HEADERS, json=payload, timeout=30)
    r.raise_for_status()
    results = r.json()["results"]
    if not results:
        print("✗ No pages found in the database.")
        sys.exit(1)
    page = results[0]
    title = "".join(
        t["plain_text"] for t in page["properties"]["Name"]["title"]
    )
    print(f"  Page: {title}")
    return page["id"]


def fetch_all_blocks(page_id: str) -> list[dict]:
    """Fetch every top-level block from a page (handles pagination)."""
    blocks: list[dict] = []
    cursor = None
    while True:
        url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
        if cursor:
            url += f"&start_cursor={cursor}"
        r = requests.get(url, headers=NOTION_HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        blocks.extend(data["results"])
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]
    return blocks


def get_block_text(block: dict) -> str:
    """Extract plain_text from any rich-text-bearing block."""
    btype = block["type"]
    container = block.get(btype, {})
    rich_text = container.get("rich_text", [])
    return "".join(t.get("plain_text", "") for t in rich_text)


def insert_toggle_after(page_id: str, after_block_id: str, furigana: str) -> None:
    """Insert a Notion toggle block (collapsed) after *after_block_id*."""
    # Notion rich_text content limit is 2000 chars per text object
    chunks = []
    remaining = furigana
    while len(remaining) > 2000:
        chunks.append(remaining[:2000])
        remaining = remaining[2000:]
    chunks.append(remaining)

    children = [
        {
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": chunk}}],
            },
        }
        for chunk in chunks
    ]

    toggle = {
        "type": "toggle",
        "toggle": {
            "rich_text": [
                {"type": "text", "text": {"content": "ふりがな（ひらがな）"}},
            ],
            "children": children,
        },
    }

    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    payload = {"children": [toggle], "after": after_block_id}
    r = requests.patch(url, headers=NOTION_HEADERS, json=payload, timeout=30)
    r.raise_for_status()


# ── Paragraph identification ────────────────────────────────────────────────
def _has_japanese(text: str) -> bool:
    return any(
        "\u3040" <= c <= "\u309f"  # hiragana
        or "\u30a0" <= c <= "\u30ff"  # katakana
        for c in text
    )


def _has_korean(text: str) -> bool:
    return any("\uac00" <= c <= "\ud7af" for c in text)


def _is_japanese_body(text: str) -> bool:
    """True if text is Japanese body content (not Korean, not a takeaway)."""
    if not text:
        return False
    if _has_korean(text):
        return False
    if not _has_japanese(text):
        return False
    # Skip 왜 중요한가 lines (Korean takeaway)
    if text.startswith("왜 "):
        return False
    return True


def identify_targets(blocks: list[dict]) -> list[tuple[int, str, str]]:
    """Return (index, block_id, text) for every paragraph needing a toggle.

    Targets:
      - Japanese body paragraphs between a 【…】heading_3 and a 📝 callout
      - Section 5 例文 sentence
      - Closing Japanese teaser paragraph
    """
    targets: list[tuple[int, str, str]] = []
    n = len(blocks)
    i = 0

    while i < n:
        b = blocks[i]
        btype = b["type"]
        text = get_block_text(b)

        # ── Story pattern: heading_3【…】 → KR translation → JP body → callout ──
        if btype == "heading_3" and text.startswith("【"):
            i += 1
            # Skip Korean heading translation in parentheses
            if i < n:
                nxt = get_block_text(blocks[i])
                if nxt.startswith("(") and _has_korean(nxt):
                    i += 1
            # Collect JP body paragraphs until callout / divider / heading
            while i < n:
                bb = blocks[i]
                bt = bb["type"]
                tt = get_block_text(bb)
                if bt in ("callout", "divider") or bt.startswith("heading"):
                    break
                if bt == "paragraph" and _is_japanese_body(tt):
                    targets.append((i, bb["id"], tt))
                i += 1
            continue

        # ── Section 5: 例文 line ──
        if btype == "paragraph" and text.startswith("例文"):
            if _has_japanese(text):
                targets.append((i, b["id"], text))
            i += 1
            continue

        # ── Closing: JP teaser (after "Issue #NN …" line, before KR teaser) ──
        if btype == "paragraph" and i >= n - 5:
            # Look for the Japanese closing paragraph that is NOT the issue line
            # and NOT Korean
            if (
                _is_japanese_body(text)
                and not text.startswith("Issue ")
                and "次号" not in text
            ):
                targets.append((i, b["id"], text))

        i += 1

    return targets


# ── Furigana generation ─────────────────────────────────────────────────────
FURIGANA_SYSTEM = """\
あなたは日本語のふりがな付与の専門家です。与えられた日本語テキストに正確なふりがなを付けてください。"""

FURIGANA_PROMPT = """\
以下の日本語段落それぞれにふりがなを付けてください。

ルール:
1. 漢字はそのまま残し、直後に丸括弧でひらがな読みを付ける。
   例: 議員連盟（ぎいんれんめい）、暗号資産（あんごうしさん）
2. カタカナ・数字・ラテン文字・句読点・記号はそのまま残す。
3. 送り仮名を正しく処理する。
   例: 求（もと）める、基（もと）づく、円建（えんだ）て
4. 元のテキストにすでに読みが括弧で示されている場合はそのまま維持する。
   例: 鮎（アユ）はそのまま鮎（アユ）とする。
5. 固有名詞（人名・社名・地名）にもふりがなを付ける。
   例: 隈研吾（くまけんご）、堀田丸正（ほったまるしょう）
6. 各段落を [番号] で区切って返す。余計な説明は付けない。

{paragraphs}
"""


def generate_furigana(paragraphs: list[tuple[int, str, str]]) -> dict[int, str]:
    """Call Claude to produce furigana for all paragraphs at once.

    Returns {local_index: furigana_text}.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build numbered paragraph list
    parts = []
    for idx, (_, _, text) in enumerate(paragraphs):
        parts.append(f"[{idx}]\n{text}")
    body = "\n\n".join(parts)

    prompt = FURIGANA_PROMPT.format(paragraphs=body)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=20000,
        system=FURIGANA_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text

    # Parse [N] delimited sections
    results: dict[int, str] = {}
    current_idx: int | None = None
    current_lines: list[str] = []

    for line in raw.split("\n"):
        stripped = line.strip()
        if stripped.startswith("[") and "]" in stripped:
            try:
                idx_str = stripped[1 : stripped.index("]")]
                idx = int(idx_str)
                if current_idx is not None:
                    results[current_idx] = "\n".join(current_lines).strip()
                current_idx = idx
                current_lines = []
                rest = stripped[stripped.index("]") + 1 :].strip()
                if rest:
                    current_lines.append(rest)
            except ValueError:
                current_lines.append(line)
        else:
            if current_idx is not None:
                current_lines.append(line)

    if current_idx is not None:
        results[current_idx] = "\n".join(current_lines).strip()

    return results


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    print("▸ Finding latest Japan Briefing page...")
    page_id = find_latest_page()

    print("▸ Fetching all blocks...")
    blocks = fetch_all_blocks(page_id)
    print(f"  {len(blocks)} blocks total.")

    print("▸ Identifying Japanese paragraphs...")
    targets = identify_targets(blocks)
    print(f"  {len(targets)} paragraphs need furigana toggles.")
    for idx, (block_idx, _, text) in enumerate(targets):
        print(f"    [{idx:2d}] block {block_idx:3d}: {text[:60]}...")

    if not targets:
        print("  Nothing to do.")
        return

    print("▸ Generating furigana via Claude...")
    furigana_map = generate_furigana(targets)
    print(f"  Got furigana for {len(furigana_map)}/{len(targets)} paragraphs.")

    # Insert in REVERSE order so earlier inserts don't shift later block positions
    print("▸ Inserting toggle blocks into Notion (reverse order)...")
    inserted = 0
    for idx in reversed(range(len(targets))):
        block_idx, block_id, text = targets[idx]
        furigana = furigana_map.get(idx)
        if not furigana:
            print(f"  ⚠ No furigana for [{idx}], skipping.")
            continue

        short = text[:50].replace("\n", " ")
        print(f"  [{idx:2d}] after block {block_idx}: {short}...")
        insert_toggle_after(page_id, block_id, furigana)
        inserted += 1
        time.sleep(RATE_LIMIT_DELAY)

    print(f"✓ Done — inserted {inserted} furigana toggles.")


if __name__ == "__main__":
    main()
