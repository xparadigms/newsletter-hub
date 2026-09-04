"""Source links, and the guard that keeps them honest.

Every generator already hands the model each item's URL, so asking it to print
the link of the story it used costs nothing. The risk is the obvious one: a
model that cannot find the right URL will happily produce a plausible-looking
one, and a wrong link is worse than no link — it looks checkable and is not.

So links are verified rather than trusted. Any 🔗 line whose URL did not come
from the scraped material is dropped before the issue is stored. Dropping is
the safe direction: the story survives without its link, and no reader is sent
somewhere the newsletter never read.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# Trailing CJK punctuation and brackets are not part of a URL. Kept narrow on
# purpose: over-trimming loses a query string, under-trimming breaks the match
# against the scraped set and the link is dropped.
URL_RE = re.compile(r"https?://[^\s<>\"'、。」）\]]+")

MARKER = "🔗"


def collect(items: Iterable[dict[str, Any]]) -> set[str]:
    """Every URL the generator actually scraped."""
    return {url for item in items if (url := (item.get("url") or "").strip())}


def _normalise(url: str) -> str:
    """Compare without the noise that never changes which page is meant."""
    return url.rstrip("/").split("#")[0]


def verify(text: str, allowed: set[str]) -> tuple[str, int, int]:
    """Strip unverifiable link lines. Returns (text, kept, dropped).

    A line is only removed when it is a link line — a 🔗 marker line whose URL
    is not in `allowed`. Prose that happens to quote a URL is left alone; the
    marker is what the prompts ask for and what the renderer styles.
    """
    known = {_normalise(u) for u in allowed}
    out: list[str] = []
    kept = dropped = 0

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped.startswith(MARKER):
            out.append(line)
            continue
        found = URL_RE.search(stripped)
        if found and _normalise(found.group(0)) in known:
            kept += 1
            out.append(line)
        else:
            dropped += 1

    return "\n".join(out), kept, dropped


def attach(text: str, items: Iterable[dict[str, Any]], label: str = "links") -> str:
    """verify() plus the log line every caller wants."""
    text, kept, dropped = verify(text, collect(items))
    note = f"  {label}: {kept} verified"
    if dropped:
        note += f", {dropped} dropped (not in the scraped material)"
    print(note)
    return text


def _headlines(text: str) -> list[str]:
    """Per-story headlines, however the newsletter happens to write them.

    The issue-level title names one story out of four or five, so excluding on
    titles alone let the rest through — and URL matching misses a story reached
    from a different outlet. These are the shapes the generators actually emit:
    【…】 for the Japanese newsletters, ### for startup's Markdown, and a
    numbered line for a Rails deep read.
    """
    found: list[str] = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("【") and "】" in line:
            found.append(line[1 : line.index("】")])
        elif line.startswith("###"):
            found.append(line.lstrip("#").strip().strip("【】"))
        elif re.match(r"^\d+\.\s+\S", line) and len(line) < 140:
            found.append(line.split(". ", 1)[1])
    return found


def already_covered(rows: list[dict[str, Any]]) -> str:
    """A prompt block naming what the recent issues already used.

    Returns "" when there is nothing to exclude, so callers can append it
    unconditionally.
    """
    if not rows:
        return ""
    titles = [r["title"] for r in rows if r.get("title")]
    urls: list[str] = []
    stories: list[str] = []
    for r in rows:
        text = r.get("source_text") or ""
        urls.extend(URL_RE.findall(text))
        stories.extend(_headlines(text))

    seen: set[str] = set()
    unique = [u for u in urls if not (u in seen or seen.add(u))]

    parts = [
        "",
        "--- ALREADY COVERED — do not use any of these again ---",
        "This is an EXTRA issue for a day that already has one. Every story must "
        "be one the issues below did not cover. Match on the EVENT, not on the "
        "wording or the URL: the same rainfall, the same earnings release or the "
        "same product launch is a repeat even when it is phrased differently or "
        "reached through a different outlet. Same-topic follow-ups are fine only "
        "if the specific development is new. If the material cannot support a "
        "full issue of genuinely new stories, write a shorter one rather than "
        "repeating.",
        "",
        "Recent issue titles:",
    ]
    parts += [f"- {t}" for t in titles]
    if stories:
        parts += ["", "Stories already covered — skip the EVENT, not just the wording:"]
        parts += [f"- {t}" for t in stories[:60]]
    if unique:
        parts += ["", "URLs already used:"]
        parts += [f"- {u}" for u in unique[:60]]
    return "\n".join(parts) + "\n"
