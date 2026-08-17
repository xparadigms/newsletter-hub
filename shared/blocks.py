"""Notion blocks → the shape the website renders.

A port of mapBlockList in web/lib/notion-map.ts. Both sides must agree exactly,
because the 318 archived issues were migrated by the TypeScript version and
every issue published from now on is written by this one. The parity test in
shared/tests/test_blocks_parity.py runs real payloads through both and diffs
the JSON.

The one intended difference: the TypeScript version fetches toggle/callout
children over the network, because it is reading pages back out of Notion. Here
the children are already inline, on block[type]["children"] — these are the
blocks we are about to *send*.

Deliberately lossy in the same ways as the TypeScript:
  - only rich-text content survives; bold, colour, links and callout icons do not
  - paragraphs that are empty after trimming are dropped
  - consecutive list items merge into a single list block
  - unhandled block types are dropped silently
"""

from __future__ import annotations

from typing import Any

Block = dict[str, Any]

# Mirrors mapBlockList's `depth < 2`, which descends two levels for toggles and
# callouts and no levels for anything else.
MAX_DEPTH = 2


def _rich_text(rt: list[dict] | None) -> str:
    """Flatten a Notion rich-text array.

    Outgoing blocks carry {"text": {"content": ...}}; blocks read back from the
    API carry "plain_text". Accept both so this also works on API responses.
    """
    out = []
    for t in rt or []:
        if not isinstance(t, dict):
            continue
        content = t.get("text", {}).get("content")
        if content is None:
            content = t.get("plain_text", "")
        out.append(content or "")
    return "".join(out)


def _children_of(block: dict, btype: str) -> list[dict]:
    body = block.get(btype) or {}
    return body.get("children") or block.get("children") or []


def strip_expiring_images(raw: list[dict]) -> list[dict]:
    """Drop Notion-hosted image blocks, recursively.

    Notion serves uploaded files from short-lived signed URLs. Rendering one per
    request is fine; persisting one makes the expiry permanent. Externally
    hosted images are kept. Mirrors stripExpiringImages in
    web/scripts/backfill-notion-to-supabase.ts.
    """
    kept = []
    for b in raw or []:
        if b.get("type") == "image":
            image = b.get("image") or {}
            if not (image.get("external") or {}).get("url"):
                continue
        for key in (b.get("type"), None):
            body = b.get(key) if key else b
            if isinstance(body, dict) and isinstance(body.get("children"), list):
                body["children"] = strip_expiring_images(body["children"])
        kept.append(b)
    return kept


def notion_blocks_to_web(raw: list[dict], depth: int = 0) -> list[Block]:
    """Convert outgoing Notion blocks into the website's Block[]."""
    blocks: list[Block] = []

    for b in raw or []:
        btype = b.get("type")
        if not btype:
            continue
        body = b.get(btype) or {}
        text = _rich_text(body.get("rich_text"))

        if btype == "paragraph":
            if text.strip():
                blocks.append({"type": "paragraph", "text": text})

        elif btype in ("heading_1", "heading_2", "heading_3"):
            blocks.append(
                {"type": "heading", "level": int(btype[-1]), "text": text}
            )

        elif btype in ("bulleted_list_item", "numbered_list_item"):
            ordered = btype == "numbered_list_item"
            last = blocks[-1] if blocks else None
            if last and last["type"] == "list" and last["ordered"] == ordered:
                last["items"].append(text)
            else:
                blocks.append({"type": "list", "ordered": ordered, "items": [text]})

        elif btype == "quote":
            blocks.append({"type": "quote", "text": text})

        elif btype in ("callout", "toggle"):
            children: list[Block] = []
            if depth < MAX_DEPTH:
                children = notion_blocks_to_web(_children_of(b, btype), depth + 1)
            blocks.append({"type": btype, "text": text, "children": children})

        elif btype == "code":
            blocks.append(
                {"type": "code", "text": text, "language": body.get("language") or ""}
            )

        elif btype == "divider":
            blocks.append({"type": "divider"})

        elif btype == "image":
            image = b.get("image") or {}
            # Same precedence as the TypeScript. Expiring Notion-hosted URLs are
            # removed by strip_expiring_images() before mapping, not here, so
            # that both mappers implement one identical rule.
            url = (image.get("file") or {}).get("url") or (
                image.get("external") or {}
            ).get("url")
            if url:
                blocks.append(
                    {
                        "type": "image",
                        "url": url,
                        "caption": _rich_text(image.get("caption")),
                    }
                )

        # Everything else is dropped, as in the TypeScript.

    return blocks


def plain_text(blocks: list[Block]) -> str:
    """Flatten Block[] to text, mirroring blockText in web/lib/text.ts."""
    parts = []
    for b in blocks:
        t = b.get("type")
        if t in ("paragraph", "heading", "quote", "code"):
            parts.append(b.get("text", ""))
        elif t == "list":
            parts.append(" ".join(b.get("items", [])))
        elif t == "pinyin":
            # Without this the Chinese body is absent from plain_text and from
            # the generated fts column — the issue would be unsearchable.
            parts.append("".join(w.get("text", "") for w in b.get("words", [])))
        elif t in ("callout", "toggle"):
            inner = [b.get("text", "")] + [
                plain_text([c]) for c in b.get("children", [])
            ]
            parts.append(" ".join(x for x in inner if x))
    return "\n".join(p for p in parts if p)
