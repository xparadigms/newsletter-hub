"""Furigana reading aids, added in memory instead of by editing a live page.

The old flow created the Notion page, read its blocks back, called Claude, then
issued ~45 sequential PATCHes at 0.35s apart — 20-40 seconds per run, and the
furigana existed only inside Notion. Here the same scan runs over the blocks we
are about to send, so there is one page create, no read-after-write, and the
toggles are present in what Supabase stores.

⚠ The trap this module exists to avoid: the original read t["plain_text"], which
is only present on blocks that came *back* from the API. Outgoing blocks carry
{"text": {"content": ...}} instead, so a naive port finds zero targets and drops
furigana silently. block_text() below reads both, and augment() raises rather
than returning quietly when a variant finds nothing.
"""

from __future__ import annotations

from typing import Any, Callable

import anthropic

Block = dict[str, Any]
# (index into the block list, the Japanese text to annotate)
Target = tuple[int, str]

FURIGANA_SYSTEM = """\
あなたは日本語のふりがな付与の専門家です。与えられた日本語テキストに正確なふりがなを付けてください。"""

# finance's prompt.
PROMPT_CALLOUT = """\
以下の日本語段落それぞれにふりがなを付けてください。

ルール:
1. 漢字はそのまま残し、直後に丸括弧でひらがな読みを付ける。
   例: 議員連盟（ぎいんれんめい）、暗号資産（あんごうしさん）
2. カタカナ・数字・ラテン文字・句読点・記号はそのまま残す。
3. 送り仮名を正しく処理する。
   例: 求（もと）める、基（もと）づく、円建（えんだ）て
4. 元のテキストにすでに読みが括弧で示されている場合はそのまま維持する。
5. 固有名詞（人名・社名・地名）にもふりがなを付ける。
6. 各段落を [番号] で区切って返す。余計な説明は付けない。

{paragraphs}
"""

# japan's prompt: same rules, two extra worked examples. Kept distinct because
# they produce measurably different output on proper nouns.
PROMPT_SECTIONS = """\
以下の日本語段落それぞれにふりがなを付けてください。

ルール:
1. 漢字はそのまま残し、直後に丸括弧でひらがな読みを付ける。
   例: 議員連盟（ぎいんれんめい）、暗号資産（あんごうしさん）
2. カタカナ・数字・ラテン文字・句読点・記号はそのまま残す。
   例: 鮎（アユ）はそのまま鮎（アユ）とする。
3. 送り仮名を正しく処理する。
   例: 求（もと）める、基（もと）づく、円建（えんだ）て
4. 元のテキストにすでに読みが括弧で示されている場合はそのまま維持する。
5. 固有名詞（人名・社名・地名）にもふりがなを付ける。
   例: 隈研吾（くまけんご）、堀田丸正（ほったまるしょう）
6. 各段落を [番号] で区切って返す。余計な説明は付けない。

{paragraphs}
"""

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 20000
TOGGLE_LABEL = "ふりがな（ひらがな）"
RICH_TEXT_LIMIT = 2000


class NoFuriganaTargets(RuntimeError):
    """A variant matched nothing. Almost always a bug, not an empty issue."""


def has_japanese_chars(text: str) -> bool:
    return any(
        "぀" <= c <= "ゟ" or "゠" <= c <= "ヿ" for c in text
    )


def has_korean_chars(text: str) -> bool:
    return any("가" <= c <= "힯" for c in text)


def is_jp_body(text: str) -> bool:
    """True for Japanese body content (not Korean, not empty)."""
    if not text or has_korean_chars(text) or not has_japanese_chars(text):
        return False
    if text.startswith("왜 "):
        return False
    return True


def block_text(block: dict) -> str:
    """Plain text of a block, from either an outgoing or a returned block."""
    btype = block.get("type")
    rt = (block.get(btype) or {}).get("rich_text", []) if btype else []
    out = []
    for t in rt:
        if not isinstance(t, dict):
            continue
        content = t.get("text", {}).get("content")
        if content is None:
            content = t.get("plain_text", "")
        out.append(content or "")
    return "".join(out)


def find_targets_callout(blocks: list[dict]) -> list[Target]:
    """finance: Japanese paragraphs following a 🇯🇵 callout."""
    targets: list[Target] = []
    n = len(blocks)
    i = 0
    while i < n:
        b = blocks[i]
        if b.get("type") == "callout":
            icon = (b.get("callout") or {}).get("icon", {}).get("emoji", "")
            if icon == "🇯🇵":
                i += 1
                while i < n:
                    bb = blocks[i]
                    bt = bb.get("type", "")
                    tt = block_text(bb)
                    if bt in ("callout", "divider") or bt.startswith("heading"):
                        break
                    if bt in ("paragraph", "bulleted_list_item") and is_jp_body(tt):
                        targets.append((i, tt))
                    i += 1
                continue
        i += 1
    return targets


def find_targets_sections(blocks: list[dict]) -> list[Target]:
    """japan: story bodies under 【…】 headings, 例文 lines, and the closing teaser."""
    targets: list[Target] = []
    n = len(blocks)
    i = 0
    while i < n:
        b = blocks[i]
        btype = b.get("type", "")
        text = block_text(b)

        # heading_3【…】 → optional KR translation → JP body → callout
        if btype == "heading_3" and text.startswith("【"):
            i += 1
            if i < n:
                nxt = block_text(blocks[i])
                if nxt.startswith("(") and has_korean_chars(nxt):
                    i += 1
            while i < n:
                bb = blocks[i]
                bt = bb.get("type", "")
                tt = block_text(bb)
                if bt in ("callout", "divider") or bt.startswith("heading"):
                    break
                if bt == "paragraph" and is_jp_body(tt):
                    targets.append((i, tt))
                i += 1
            continue

        if btype == "paragraph" and text.startswith("例文") and has_japanese_chars(text):
            targets.append((i, text))
            i += 1
            continue

        if btype == "paragraph" and i >= n - 5:
            if is_jp_body(text) and not text.startswith("Issue ") and "次号" not in text:
                targets.append((i, text))

        i += 1
    return targets


VARIANTS: dict[str, tuple[Callable[[list[dict]], list[Target]], str]] = {
    "callout": (find_targets_callout, PROMPT_CALLOUT),
    "sections": (find_targets_sections, PROMPT_SECTIONS),
}


def generate_batch(targets: list[Target], api_key: str, prompt: str) -> dict[int, str]:
    """One Claude call for every paragraph, returned keyed by target position."""
    client = anthropic.Anthropic(api_key=api_key)
    parts = [f"[{idx}]\n{text}" for idx, (_, text) in enumerate(targets)]
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=FURIGANA_SYSTEM,
        messages=[{"role": "user", "content": prompt.format(paragraphs="\n\n".join(parts))}],
    )

    raw = resp.content[0].text
    results: dict[int, str] = {}
    cur_idx: int | None = None
    cur_lines: list[str] = []
    for line in raw.split("\n"):
        stripped = line.strip()
        if stripped.startswith("[") and "]" in stripped:
            try:
                idx = int(stripped[1 : stripped.index("]")])
            except ValueError:
                cur_lines.append(line)
                continue
            if cur_idx is not None:
                results[cur_idx] = "\n".join(cur_lines).strip()
            cur_idx = idx
            cur_lines = []
            rest = stripped[stripped.index("]") + 1 :].strip()
            if rest:
                cur_lines.append(rest)
        elif cur_idx is not None:
            cur_lines.append(line)
    if cur_idx is not None:
        results[cur_idx] = "\n".join(cur_lines).strip()
    return results


def _toggle_block(furigana: str) -> dict:
    chunks = [
        furigana[i : i + RICH_TEXT_LIMIT]
        for i in range(0, max(len(furigana), 1), RICH_TEXT_LIMIT)
    ]
    return {
        "type": "toggle",
        "toggle": {
            "rich_text": [{"type": "text", "text": {"content": TOGGLE_LABEL}}],
            "children": [
                {
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": c}}]
                    },
                }
                for c in chunks
            ],
        },
    }


def augment(blocks: list[dict], *, variant: str, api_key: str) -> list[dict]:
    """Return a copy of `blocks` with a furigana toggle after each JP paragraph.

    Raises NoFuriganaTargets when the variant matches nothing — that is the
    signature of a broken port, and it must not pass silently.
    """
    finder, prompt = VARIANTS[variant]
    targets = finder(blocks)
    print(f"▸ Furigana: {len(targets)} Japanese paragraphs found.")
    if not targets:
        raise NoFuriganaTargets(
            f"variant {variant!r} matched no Japanese paragraphs in "
            f"{len(blocks)} blocks"
        )

    furigana_map = generate_batch(targets, api_key, prompt)
    print(f"  generated for {len(furigana_map)}/{len(targets)} paragraphs.")

    out = list(blocks)
    # Reverse order so earlier indices stay valid as we splice.
    for idx in reversed(range(len(targets))):
        position, _ = targets[idx]
        furigana = furigana_map.get(idx)
        if not furigana:
            continue
        out.insert(position + 1, _toggle_block(furigana))
    print(f"  ✓ {len(out) - len(blocks)} furigana toggles inserted.")
    return out
