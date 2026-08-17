"""shared/blocks.py must agree exactly with web/lib/notion-map.ts.

The 318 archived issues were migrated by the TypeScript mapper; every issue
published from now on is written by the Python one. If they diverge, the archive
and the new issues render differently and nothing in either codebase notices.

Runs the same payloads through both and diffs the JSON.

    python3 shared/tests/test_blocks_parity.py

Needs node + npx (it shells out to web/scripts/map-blocks-harness.ts). It is a
development-time check, not part of any workflow.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared import blocks as B  # noqa: E402
from shared import trilingual  # noqa: E402


def _rt(content: str) -> list[dict]:
    return [{"type": "text", "text": {"content": content}}]


def _para(text: str) -> dict:
    return {"type": "paragraph", "paragraph": {"rich_text": _rt(text)}}


# Every branch of the mapper, including the ones with no natural fixture.
EXHAUSTIVE: list[dict] = [
    {"type": "heading_1", "heading_1": {"rich_text": _rt("H1")}},
    {"type": "heading_2", "heading_2": {"rich_text": _rt("H2")}},
    {"type": "heading_3", "heading_3": {"rich_text": _rt("H3")}},
    _para("A normal paragraph."),
    _para("   "),  # dropped: empty after trim
    _para(""),  # dropped
    {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rt("b1")}},
    {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rt("b2")}},
    # Ordered-ness change must start a new list rather than extend the previous.
    {"type": "numbered_list_item", "numbered_list_item": {"rich_text": _rt("n1")}},
    {"type": "numbered_list_item", "numbered_list_item": {"rich_text": _rt("n2")}},
    _para("Interrupting paragraph."),
    # A run after an interruption is a third list.
    {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rt("b3")}},
    {"type": "quote", "quote": {"rich_text": _rt("A quotation.")}},
    {"type": "divider", "divider": {}},
    {"type": "code", "code": {"rich_text": _rt("print(1)"), "language": "python"}},
    {"type": "code", "code": {"rich_text": _rt("bare")}},  # missing language → ""
    {
        "type": "callout",
        "callout": {
            "rich_text": _rt("日本語"),
            "icon": {"emoji": "🇯🇵"},
            "children": [_para("Callout child.")],
        },
    },
    {
        "type": "toggle",
        "toggle": {
            "rich_text": _rt("ふりがな（ひらがな）"),
            "children": [
                _para("暗号資産（あんごうしさん）"),
                # Nesting: depth 1 → its children are depth 2, still mapped.
                {
                    "type": "toggle",
                    "toggle": {
                        "rich_text": _rt("nested"),
                        "children": [_para("deep")],
                    },
                },
            ],
        },
    },
    {
        "type": "image",
        "image": {"external": {"url": "https://example.com/a.png"}, "caption": _rt("cap")},
    },
    {"type": "image", "image": {"external": {"url": "https://example.com/b.png"}}},
    # Unhandled types are dropped by both.
    {"type": "table_of_contents", "table_of_contents": {}},
    {"type": "bookmark", "bookmark": {"url": "https://example.com"}},
    {"type": "to_do", "to_do": {"rich_text": _rt("task"), "checked": False}},
]

TRILINGUAL_MD = """\
## 01 / Market

**Stripe acquires OpenRouter**

- Deal closed Tuesday
- Reported at $7B

<details>
<summary>ふりがな</summary>
暗号資産（あんごうしさん）の取引（とりひき）
</details>

<callout>
스트라이프가 OpenRouter를 인수했다.
</callout>

---

### 02 / Rails

왜 중요한가: 결제 인프라의 재편.
"""


def map_with_typescript(payload: list[dict]) -> list[dict]:
    proc = subprocess.run(
        ["npx", "tsx", "scripts/map-blocks-harness.ts"],
        cwd=ROOT / "web",
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"harness failed:\n{proc.stderr}")
    return json.loads(proc.stdout)


def check(name: str, payload: list[dict]) -> bool:
    py = B.notion_blocks_to_web(payload)
    ts = map_with_typescript(payload)
    if py == ts:
        print(f"ok   {name}: {len(py)} blocks identical")
        return True

    print(f"FAIL {name}")
    py_s = json.dumps(py, ensure_ascii=False, indent=2).split("\n")
    ts_s = json.dumps(ts, ensure_ascii=False, indent=2).split("\n")
    import difflib

    for line in list(difflib.unified_diff(ts_s, py_s, "typescript", "python", n=2))[:60]:
        print("   " + line.rstrip())
    return False


def main() -> int:
    cases = [
        ("exhaustive", EXHAUSTIVE),
        ("trilingual markdown", trilingual.md_to_blocks(TRILINGUAL_MD)),
    ]
    ok = all([check(name, payload) for name, payload in cases])
    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
