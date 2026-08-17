"""Guards on the furigana port.

The bug this is here to catch: the original _block_plain_text read
t["plain_text"], which only exists on blocks that came back from the Notion API.
The blocks we now scan are the ones we are about to send, and they carry
{"text": {"content": ...}} instead. A naive port finds zero targets, inserts no
toggles, raises nothing, and logs "0 Japanese paragraphs found" — the issue
publishes without furigana and nobody notices.

    python3 shared/tests/test_furigana.py
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared import furigana as F  # noqa: E402

JP = "暗号資産の取引が拡大している。"
JP2 = "金融庁は新しい制度を検討している。"


def outgoing(btype: str, text: str, **body) -> dict:
    """A block as the generators build it: text.content, no plain_text."""
    return {
        "type": btype,
        btype: {"rich_text": [{"type": "text", "text": {"content": text}}], **body},
    }


def returned(btype: str, text: str, **body) -> dict:
    """A block as the Notion API returns it: plain_text present."""
    return {
        "type": btype,
        btype: {
            "rich_text": [
                {"type": "text", "text": {"content": text}, "plain_text": text}
            ],
            **body,
        },
    }


failures: list[str] = []


def expect(name: str, actual, wanted) -> None:
    if actual == wanted:
        print(f"ok   {name}")
    else:
        failures.append(name)
        print(f"FAIL {name}\n       wanted: {wanted!r}\n       actual: {actual!r}")


# 1. block_text must read both shapes. This is the whole trap.
expect("block_text reads outgoing text.content", F.block_text(outgoing("paragraph", JP)), JP)
expect("block_text reads returned plain_text", F.block_text(returned("paragraph", JP)), JP)

# 2. The finance variant must find targets in OUTGOING blocks.
finance_blocks = [
    outgoing("heading_2", "SECTION"),
    outgoing("callout", "日本語", icon={"emoji": "🇯🇵"}),
    outgoing("paragraph", JP),
    outgoing("paragraph", "이것은 한국어입니다"),  # Korean → not a target
    outgoing("bulleted_list_item", JP2),
    outgoing("divider", ""),  # stops the run
    outgoing("paragraph", JP),  # after the divider → not a target
]
expect(
    "find_targets_callout on outgoing blocks",
    F.find_targets_callout(finance_blocks),
    [(2, JP), (4, JP2)],
)

# 3. The japan variant, likewise.
japan_blocks = [
    outgoing("heading_3", "【ニュース】"),
    outgoing("paragraph", "(한국어 번역)"),  # skipped translation line
    outgoing("paragraph", JP),
    outgoing("callout", "translation"),  # stops the run
    outgoing("paragraph", "例文: " + JP2),
]
expect(
    "find_targets_sections on outgoing blocks",
    F.find_targets_sections(japan_blocks),
    [(2, JP), (4, "例文: " + JP2)],
)

# 4. Zero targets must raise, not pass quietly.
try:
    F.augment([outgoing("paragraph", "All English here.")], variant="callout", api_key="x")
    expect("augment raises when nothing matches", "no exception", "NoFuriganaTargets")
except F.NoFuriganaTargets:
    print("ok   augment raises when nothing matches")

# 5. Toggles land directly after their paragraph, and earlier indices survive
#    the splice of later ones.
F.generate_batch = lambda targets, api_key, prompt: {  # type: ignore[assignment]
    i: f"よみ{i}" for i in range(len(targets))
}
out = F.augment(finance_blocks, variant="callout", api_key="x")
expect("augment inserts one toggle per target", len(out), len(finance_blocks) + 2)
expect("first toggle follows its paragraph", out[3]["type"], "toggle")
expect("second toggle follows its list item", out[6]["type"], "toggle")
expect(
    "toggle carries the generated reading",
    F.block_text(out[3]["toggle"]["children"][0]),
    "よみ0",
)
expect("blocks before the first target are untouched", out[:3], finance_blocks[:3])

print("\nPASS" if not failures else f"\nFAIL ({len(failures)})")
raise SystemExit(1 if failures else 0)
