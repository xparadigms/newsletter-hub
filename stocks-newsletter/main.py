#!/usr/bin/env python3
"""Three Companies — a daily public company newsletter, in Japanese.

Three listed companies a day: two that were in the news over the last 30 days
and one wildcard. Each company is its own article, written in Japanese with a
full Korean translation under every paragraph and furigana on the Japanese,
the same reading format as Business Insight.

Three passes, because each one fails differently:

1. Research. Claude with the web search tool picks the companies and gathers
   the last 30 days of news, with dates, figures and URLs. Nothing about a
   price or an event may come from the model's memory.
2. Prices. Yahoo Finance's daily closes give the last close and the 30 day,
   six month and one year changes by arithmetic rather than by search, so the
   numbers in the basic info line are computed, not recalled. If Yahoo does
   not answer for a symbol, the researched figures are used instead.
3. Writing. One call writes the shared backdrop and all three companies, so
   they read as one edition, and the script splits it into three articles.

Links are verified the way every other generator verifies them: a 🔗 line
survives only if its URL came back from the web search.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any

import anthropic
import requests

# The workflow runs with this project as the working directory, so the repo root
# is not importable. Python only puts the *script's* directory on sys.path.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from shared import audio, furigana, issue as issue_row, llm, plaintext, sources, store  # noqa: E402

SECTION = "stocks"
SERIES = "Three Companies"
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
KST = timezone(timedelta(hours=9))
EDITION = int(os.environ.get("EDITION", "1"))
MODEL = "claude-sonnet-4-6"

# Companies inside this window are not picked again. Titles carry the ticker,
# so the last 30 days of titles are the exclusion list.
REPEAT_WINDOW_DAYS = 30

DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━━━━━"


# ── Pass 1: research ────────────────────────────────────────────────────────
RESEARCH_SYSTEM = """\
You are the research desk for a daily public company newsletter read by senior \
bank executives in Korea. You find facts; someone else writes. Use the web \
search tool for every price, market cap and event. Never rely on memory for \
prices or events: if a search does not confirm something, leave it out.\
"""

RESEARCH_PROMPT = """\
Today is {today} (Korea time). Research today's edition.

First search current market news to understand the macro setting: rates, \
energy, AI capex, US China trade, Asian markets.

Then pick three public companies from any exchange:
1. Two must be "hot" in the last 30 days: a major earnings event, deal, \
regulatory action, contract, index inclusion, sharp price move, or heavy news \
flow. Prefer companies whose news connects to a live macro theme (rates, \
energy, AI capex, US China trade, Asia).
2. The third is a wildcard chosen on judgment, with no criteria.
3. Vary market cap. At most one company above $500 billion. Include at least \
one company below $20 billion unless today's news makes that unreasonable.
4. Rotate sectors and geographies. The three should be in three different \
industries.
5. Do not pick any company covered in the last {window} days:
{recent}

For each company, search for its latest price, market cap and news from the \
last 30 days. Record dates and figures exactly as the sources state them, and \
note which source said what.

Finish with ONLY a JSON object, no prose before or after, in this shape:
{{
  "backdrop": "4 to 6 sentences of macro facts for today with dates and sources",
  "companies": [
    {{
      "name": "Company name as it is usually written in English",
      "ticker": "ticker as usually quoted, e.g. NVDA, 005930, 7203",
      "exchange": "e.g. NASDAQ, KRX, TSE, HKEX",
      "yahoo_symbol": "the Yahoo Finance symbol, e.g. NVDA, 005930.KS, 7203.T, 0700.HK",
      "currency": "USD, KRW, JPY ...",
      "role": "hot or wildcard",
      "industry": "the industry in a few words",
      "country": "headquarters country",
      "market_cap": "approximate market cap with currency and a USD figure, with source",
      "valuation": "one valuation or yield figure with source, e.g. forward P/E or dividend yield",
      "price_note": "latest close and date as a source reports it",
      "events": ["YYYY-MM-DD: what happened, with figures, per SOURCE"],
      "industry_notes": "how the sector works and where this company sits in it",
      "why_notes": "implications for markets, policy, the wider economy, and Korea, Japan and Asia where relevant",
      "urls": ["the URLs of the pages the facts above came from"]
    }}
  ]
}}
"""

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 30}


def _last_json_object(text: str) -> dict[str, Any] | None:
    """The last top-level JSON object in `text` that has a companies list.

    Search results arrive as text blocks too, and the model sometimes talks
    before the JSON, so the object is found by decoding rather than by slicing.
    """
    decoder = json.JSONDecoder()
    found = None
    i = text.find("{")
    while i != -1:
        try:
            obj, end = decoder.raw_decode(text, i)
        except ValueError:
            i = text.find("{", i + 1)
            continue
        if isinstance(obj, dict) and "companies" in obj:
            found = obj
        i = text.find("{", end)
    return found


def research(today: str, recent: list[str]) -> tuple[dict[str, Any], set[str]]:
    """Pick three companies and gather their facts. Returns (research, URLs seen)."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages: list[dict[str, Any]] = [{
        "role": "user",
        "content": RESEARCH_PROMPT.format(
            today=today,
            window=REPEAT_WINDOW_DAYS,
            recent="\n".join(f"   - {t}" for t in recent) or "   (none yet)",
        ),
    }]
    urls: set[str] = set()
    text_parts: list[str] = []

    # A server tool loop can stop at pause_turn; sending the turn back as it
    # stands lets it carry on. Bounded so a stuck loop cannot bill forever.
    for _ in range(6):
        with client.messages.stream(
            model=MODEL,
            max_tokens=16000,
            system=RESEARCH_SYSTEM,
            tools=[WEB_SEARCH_TOOL],
            messages=messages,
        ) as stream:
            final = stream.get_final_message()
        u = final.usage
        print(f"  research: {u.input_tokens:,} in, {u.output_tokens:,} out, stop={final.stop_reason}")

        for block in final.content:
            if block.type == "web_search_tool_result" and isinstance(block.content, list):
                urls.update(r.url for r in block.content if getattr(r, "url", None))
            elif block.type == "text":
                text_parts.append(block.text)
                for c in getattr(block, "citations", None) or []:
                    if getattr(c, "url", None):
                        urls.add(c.url)

        if final.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": final.content})

    text = "".join(text_parts)
    data = _last_json_object(text)
    if data is None:
        raise RuntimeError(f"research did not end in JSON: {text[-800:]!r}")
    companies = data.get("companies") or []
    if len(companies) != 3:
        raise RuntimeError(f"research returned {len(companies)} companies, expected 3")
    print(f"  {len(urls)} URLs from search")
    return data, urls


# ── Pass 2: prices ──────────────────────────────────────────────────────────
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=2y&interval=1d"


def _close_on_or_before(series: list[tuple[date, float]], target: date) -> float | None:
    earlier = [c for d, c in series if d <= target]
    return earlier[-1] if earlier else None


def price_facts(symbol: str) -> dict[str, Any] | None:
    """Last close and 30 day / 6 month / 1 year changes from daily closes."""
    try:
        resp = requests.get(
            YAHOO.format(symbol=symbol),
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        resp.raise_for_status()
        result = resp.json()["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
        series = [
            (datetime.fromtimestamp(t, timezone.utc).date(), c)
            for t, c in zip(result["timestamp"], closes)
            if c is not None
        ]
    except Exception as e:  # noqa: BLE001 — the researched figures still stand
        print(f"  ⚠ Yahoo {symbol}: {e}")
        return None
    if len(series) < 30:
        print(f"  ⚠ Yahoo {symbol}: only {len(series)} closes")
        return None

    last_day, last = series[-1]
    year = [c for d, c in series if d > last_day - timedelta(days=365)]

    def change(days: int) -> str | None:
        then = _close_on_or_before(series, last_day - timedelta(days=days))
        return f"{(last / then - 1) * 100:+.0f}%" if then else None

    meta = result.get("meta", {})
    return {
        "symbol": symbol,
        "currency": meta.get("currency"),
        "last_close": round(last, 2),
        "last_close_date": last_day.isoformat(),
        "change_30d": change(30),
        "change_6m": change(182),
        "change_1y": change(365),
        "range_52w": f"{min(year):,.2f} to {max(year):,.2f} (daily closes)",
    }


# ── Pass 3: writing ─────────────────────────────────────────────────────────
WRITE_SYSTEM = """\
You write "Three Companies", a daily public company newsletter in Japanese, for \
senior readers such as bank executives who read Japanese at roughly N2 and \
Korean natively.

WRITING RULES
- Clear, direct, professional sentences. State who is doing what and why it \
matters. No vague or metaphorical phrasing.
- No rhetorical contrast constructions such as 「XではなくY」「XというよりY」, or \
their Korean equivalents 「X가 아니라 Y」.
- Every paragraph has at most three sentences.
- Never use em dashes, en dashes or hyphens anywhere: no —, –, ―, ‐ or -. \
Write "30 day" and "long term" style compounds without a hyphen, and write \
negative moves in words (約9%下落). The katakana long vowel mark ー is fine.
- Institution and company names are written in English only, exactly as the \
institution writes them in English, in both languages: Bank of Korea, Federal \
Reserve, Bank of Japan, Samsung Electronics. Never add a Japanese or Korean \
name in parentheses.
- Round percentages and mark them approximate: 約12%上昇 / 약 12% 상승.
- Attribute figures and claims to their sources in plain prose (Reutersによると).
- Never give investment recommendations. No 買い, 売り or target prices of your own.
- Use only facts from the research and price data you are given. Prices are \
approximate closing levels of the most recent trading day.

LANGUAGES
- Japanese: natural business Japanese, です・ます体. Real market vocabulary: \
時価総額, 決算, 受注, 設備投資, 利回り.
- Korean: 평어체. Every Korean sentence ends in the plain declarative form \
(~다 / ~이다 / ~했다), the register Korean newspapers use. Never ~습니다 or ~요.
- Every Japanese paragraph is followed by a FULL Korean translation with the \
same number of sentences, in the same order, carrying every name, number and \
qualifier. A Korean paragraph shorter than its Japanese is a defect.\
"""

WRITE_PROMPT = """\
Write today's edition, {weekday}. Output plain text only, no Markdown.

Use exactly this layout. Lines in CAPITALS followed by a colon are markers the \
script reads; keep them exactly.

BACKDROP:
[Japanese: 3 to 4 sentences on the macro setting today]
📝 한국어 번역:
[Korean translation]

Then three company blocks, in this order: the two hot companies, then the \
wildcard.

=== COMPANY ===
TITLE: Company Name (TICKER): A Short Descriptive Subtitle In Title Case
BASIC:
[Japanese: one paragraph with price, market cap, 30 day change, six month \
change, one year change, 52 week range, and one valuation or yield figure where \
relevant. Use the PRICE DATA where it is given; otherwise the researched \
figures. At most three sentences.]
📝 한국어 번역:
[Korean]
WHAT:
[Japanese: the specific events of the last 30 days with dates and figures. One \
or two paragraphs, each followed by its Korean translation under 📝 한국어 번역:]
INDUSTRY:
[Japanese: how the sector works and where this company sits in it. One or two \
paragraphs, each followed by its Korean translation.]
WHY:
[Japanese: implications for markets, policy, the wider economy, and where \
relevant for Korea, Japan and Asia. One or two paragraphs, each followed by its \
Korean translation.]
SOURCES:
🔗 [URL from this company's research, copied exactly]
🔗 [one to three lines]

LENGTH: WHAT, INDUSTRY and WHY together run 700 to 900 Japanese characters per \
company, excluding BASIC and excluding the Korean. The TITLE is English, in \
Title Case, with no hyphens or dashes.

--- RESEARCH ---
{research}

--- PRICE DATA (computed from daily closes) ---
{prices}
"""

_DASHES = str.maketrans({"—": "、", "–": "、", "―": "、", "‐": " ", "‑": " "})
_ASCII_HYPHEN = re.compile(r"(?<=[0-9A-Za-z]) ?- ?(?=[0-9A-Za-z])")


def _no_dashes(line: str, *, japanese: bool) -> str:
    """Enforce the no dash rule the model sometimes forgets. Links are exempt."""
    if line.lstrip().startswith(sources.MARKER):
        return line
    if not japanese:
        line = line.replace(" — ", ", ").replace(" – ", ", ")
    line = line.translate(_DASHES)
    return _ASCII_HYPHEN.sub(" ", line)


def write_edition(data: dict[str, Any], prices: list[dict | None], weekday: str) -> str:
    return llm.complete(
        model=MODEL,
        system=WRITE_SYSTEM,
        user=WRITE_PROMPT.format(
            weekday=weekday,
            research=json.dumps(data, ensure_ascii=False, indent=2),
            prices=json.dumps(
                [p for p in prices if p], ensure_ascii=False, indent=2
            ) or "(none: use the researched figures)",
        ),
        max_tokens=20000,
        label="write",
    )


# ── Assembly ────────────────────────────────────────────────────────────────
PARTS = [
    ("BASIC", "【基本情報】(기본 정보)"),
    ("WHAT", "【直近30日の動き】(최근 30일의 움직임)"),
    ("INDUSTRY", "【業界の構造】(산업 구조)"),
    ("WHY", "【なぜ重要か】(왜 중요한가)"),
]
_MARKER = re.compile(r"^(BACKDROP|BASIC|WHAT|INDUSTRY|WHY|SOURCES):\s*$")


def _sections(block: str) -> dict[str, list[str]]:
    """Lines under each MARKER: line, keyed by marker."""
    out: dict[str, list[str]] = {}
    key = None
    for raw in block.split("\n"):
        line = raw.strip()
        m = _MARKER.match(line)
        if m:
            key = m.group(1)
            out[key] = []
        elif key and line:
            out[key].append(line)
    return out


def _clean(lines: list[str]) -> list[str]:
    return [
        _no_dashes(line, japanese=furigana.has_japanese_chars(line)) for line in lines
    ]


def split_edition(text: str) -> tuple[list[str], list[tuple[str, dict[str, list[str]]]]]:
    """(backdrop lines, [(title, sections)]) from the writer's output."""
    head, *blocks = text.split("=== COMPANY ===")
    backdrop = _clean(_sections(head).get("BACKDROP", []))
    companies = []
    for block in blocks:
        m = re.search(r"^TITLE:\s*(.+)$", block, re.M)
        if not m:
            raise RuntimeError(f"company block without a TITLE line: {block[:200]!r}")
        title = _no_dashes(m.group(1).strip(), japanese=False)
        companies.append((title, {k: _clean(v) for k, v in _sections(block).items()}))
    if len(companies) != 3 or not backdrop:
        raise RuntimeError(
            f"writer returned {len(companies)} companies and "
            f"{len(backdrop)} backdrop lines; expected 3 and some"
        )
    return backdrop, companies


def article_text(
    headline: str, part: int, backdrop: list[str], sections: dict[str, list[str]]
) -> str:
    """One company as the plain-text format plaintext.to_notion_blocks reads."""
    lines = [f"{headline} · {part}/3", DIVIDER, "【市場の背景】(시장 배경)", *backdrop]
    for key, heading in PARTS:
        lines += [DIVIDER, heading, *sections.get(key, [])]
    links = [line for line in sections.get("SOURCES", []) if line.startswith(sources.MARKER)]
    if links:
        lines += [DIVIDER, "【出典】(출처)", *links]
    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────────
def _recent_companies() -> list[str]:
    if not store.configured():
        return []
    # Three articles a day, so a 30 day window is up to ~90 titles.
    return store.recent_titles(SECTION, limit=3 * REPEAT_WINDOW_DAYS)


def run() -> None:
    now = datetime.now(KST)
    today_iso = now.strftime("%Y-%m-%d")
    weekday = now.strftime("%A, %B %-d, %Y")
    headline = f"Three Companies, Three Industries: {weekday}"
    dry_run = "--dry-run" in sys.argv
    print(f"▸ {headline} (edition {EDITION})")

    recent = _recent_companies()
    print(f"▸ Researching with web search ({len(recent)} recent titles excluded)...")
    data, urls = research(weekday, recent)
    for c in data["companies"]:
        print(f"  {c.get('role', '?'):8} {c.get('name')} ({c.get('yahoo_symbol')}) · {c.get('industry')}")

    print("▸ Price history from Yahoo Finance...")
    prices = [price_facts(c.get("yahoo_symbol") or "") for c in data["companies"]]
    for p in prices:
        if p:
            print(f"  {p['symbol']}: {p['last_close']} {p['currency']} on {p['last_close_date']}, "
                  f"30d {p['change_30d']}, 6m {p['change_6m']}, 1y {p['change_1y']}")

    print("▸ Writing...")
    backdrop, companies = split_edition(write_edition(data, prices, weekday))

    number = int(os.environ.get("ISSUE_NUMBER") or 0) or store.next_issue_number(
        SECTION, today_iso, EDITION
    )
    articles = []
    for part, (title, sections) in enumerate(companies, start=1):
        text = sources.attach(article_text(headline, part, backdrop, sections), [
            {"url": u} for u in urls
        ], label=f"links {part}/3")
        articles.append((part, f"[{SERIES} #{number} · {part}/3] ({title})", text))

    if dry_run:
        for _, raw_title, text in articles:
            print("\n" + "=" * 60 + f"\n{raw_title}\n" + "=" * 60 + f"\n{text}")
        print("\n(dry run — nothing written)")
        return

    # Stored last to first: the list orders a day by published_at, newest on
    # top, so writing part 1 last puts it first.
    for part, raw_title, text in reversed(articles):
        print(f"▸ {raw_title}")
        blocks = plaintext.to_notion_blocks(text)
        try:
            blocks = furigana.augment(
                blocks, variant="sections", api_key=ANTHROPIC_API_KEY, group_by_story=True
            )
        except Exception as e:  # noqa: BLE001 — publish without furigana rather than not at all
            print(f"  ⚠ Furigana failed (non-fatal): {e}")

        row = issue_row.build_row(
            section=SECTION,
            issue_date=today_iso,
            raw_title=raw_title,
            notion_blocks=blocks,
            source_text=text,
            source_format="plain",
            edition=EDITION,
            part=part,
        )
        try:
            print(f"  ✓ Audio: {audio.attach_audio(row['blocks'], 'ja')} block(s)")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ Audio failed (non-fatal): {e}")

        stored = store.upsert_issue(row)
        if stored.get("slug"):
            print(f"  ✓ Stored: {SECTION}/{stored['slug']}")
            store.ping_revalidate(SECTION, stored["slug"])

    for _, raw_title, text in articles:
        print("\n" + "=" * 60 + f"\n{raw_title}\n" + "=" * 60 + f"\n{text}")


if __name__ == "__main__":
    run()
