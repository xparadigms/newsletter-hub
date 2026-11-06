#!/usr/bin/env python3
"""Rebuild a stored China issue's blocks from its own source text.

    python3 rerender.py            # dry run: report what would change
    python3 rerender.py --commit   # write the new blocks back

Segmentation and block structure change over time; the issue text does not.
Re-running main.py would re-scrape and re-prompt, producing a *different* issue —
fine for publishing today's news, useless for applying a parser fix to something
already published. This reads the stored `source_text` and puts it through the
current build_blocks, so the words are identical and only the structure moves.

Issues are now published as one article per story (shared/split.py), and every
article stores the whole issue's source text. An article's row is rebuilt by
building the whole issue and taking its own part (the :pN of its run_key)
through the same split the generator used. Rows from before the split hold the
whole issue and are rebuilt whole, as before.

Needs SUPABASE_URL and SUPABASE_SECRET_KEY.
"""

from __future__ import annotations

import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from shared import audio  # noqa: E402
from shared import blocks as blocks_mod  # noqa: E402
from shared import markers as china_blocks  # noqa: E402
from shared import split, store  # noqa: E402
from shared.http import request_with_retry  # noqa: E402

COMMIT = "--commit" in sys.argv
_PART = re.compile(r":p(\d+)$")


def rebuild(run_key: str, source_text: str) -> tuple[list[dict], int, int] | None:
    """(blocks, story_count, unsegmented) for one stored row, or None when the
    issue no longer splits into as many articles as the row's part number.
    `unsegmented` counts the whole issue's lines, since that is what was built."""
    blocks, stories, unsegmented = china_blocks.build_blocks(source_text)
    m = _PART.search(run_key)
    if not m:
        return blocks, stories, unsegmented
    parts, _ = split.split_parts(blocks, **split.RULES["china"])
    merged = split.merge_parts(
        "china", [(split.story_title("china", p), p) for p in parts], None
    )
    n = int(m.group(1))
    if n > len(merged):
        return None
    part = merged[n - 1][1]
    return part, sum(1 for b in part if b.get("type") == "heading"), unsegmented


def fetch_rows() -> list[dict]:
    url = (os.environ["SUPABASE_URL"]).rstrip("/")
    key = os.environ["SUPABASE_SECRET_KEY"]
    resp = request_with_retry(
        "GET",
        f"{url}/rest/v1/newsletter"
        "?section=eq.china&select=slug,run_key,source_text,blocks,plain_text"
        "&order=issue_date.desc",
        label="Supabase",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    resp.raise_for_status()
    return resp.json()


def summarise(blocks: list[dict]) -> str:
    counts: dict[str, int] = {}
    for b in blocks:
        counts[b["type"]] = counts.get(b["type"], 0) + 1
    return ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))


def main() -> int:
    rows = fetch_rows()
    if not rows:
        print("No china issues stored.")
        return 0

    changed = 0
    for row in rows:
        if not row.get("source_text"):
            print(f"  ! {row['slug']} has no source_text — skipped")
            continue

        rebuilt = rebuild(row["run_key"], row["source_text"])
        if rebuilt is None:
            print(f"  ! {row['slug']}: the issue no longer splits into {row['run_key']} — skipped")
            continue
        blocks, stories, unsegmented = rebuilt
        # Stored blocks carry `audio`; freshly built ones do not, so without
        # this every row reads as "changed" and --commit would PATCH the audio
        # away. Carry each sentence's existing clip over first — the cache key
        # changed with the voice, so a lookup alone would not find it — and let
        # attach_audio voice only what never had one.
        clips = {
            "".join(w.get("text", "") for w in b.get("words", [])): b["audio"]
            for b in row["blocks"]
            if b.get("type") == "pinyin" and b.get("audio")
        }
        for b in blocks:
            text = "".join(w.get("text", "") for w in b.get("words", []))
            if b.get("type") == "pinyin" and text in clips:
                b["audio"] = clips[text]
        try:
            audio.attach_audio(blocks, "zh")
        except Exception as e:  # noqa: BLE001
            print(f"    ⚠ audio lookup failed (non-fatal): {e}")
        plain = blocks_mod.plain_text(blocks)

        same_blocks = blocks == row["blocks"]
        # The words must not move. If plain_text changes, the parser dropped or
        # invented text and this is not a re-render — stop rather than write it.
        same_text = plain == (row.get("plain_text") or "")

        print(f"  {row['slug']}")
        print(f"    before: {summarise(row['blocks'])}")
        print(f"    after : {summarise(blocks)}   ({stories} stories, {unsegmented} unsegmented)")
        print(f"    blocks identical: {same_blocks}   plain_text identical: {same_text}")

        if not same_text:
            print("    ✗ REFUSING: plain_text changed, so this is not a pure re-render.")
            continue
        if same_blocks:
            print("    nothing to do")
            continue

        changed += 1
        if COMMIT:
            store.patch_issue(row["run_key"], {"blocks": blocks, "plain_text": plain})
            store.ping_revalidate("china", row["slug"])
            print("    ✓ written and revalidated")

    if not COMMIT and changed:
        print(f"\n{changed} issue(s) would change. Re-run with --commit to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
