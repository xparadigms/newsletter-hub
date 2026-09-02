# Japan Daily Talk — Project Instructions

A daily Japanese newsletter written as a conversation, for Heechang (one reader). General
Japan news — politics, the economy, technology, daily life, and whatever is trending. It
doubles as Japanese reading practice, which is why every Japanese line carries its own Korean
line and every story ends with a furigana toggle.

> Note: `main.py` does not read this file. `load_claude_prompt()` exists but is never called —
> the live prompt is `SYSTEM_PROMPT` / `ISSUE_PROMPT` inside `main.py`. Change both together.

---

## How to run an issue

When I say **"run today's issue"**, produce a complete issue using the format below. No
clarifying questions, no preamble.

`python3 main.py --dry-run` prints the issue and writes nothing — use it while iterating on
format. Without the flag it publishes to Supabase, Notion and Calendar.

---

## Voice & stance

- **Audience: me, alone.** Not published.
- **It is a dialogue, not a report.** Two people:
  - **ハル** — a journalist living in Tokyo. Gives the fact, the number, the source.
  - **ミン** — from Seoul, learning Japanese. Asks what a foreigner would ask.
- **Every Japanese line is immediately followed by its own Korean line.** Never group the
  Korean, never summarise it. One Japanese line, then that line in Korean, then the next.
- **Japanese:** natural spoken register, current vocabulary from the news. Not written-report
  Japanese, not textbook Japanese.
- **Korean:** casual-professional (반말 OK), the way you'd explain it to a friend.
- **Concrete.** Name the ministry, the company, the number, the date. Cite the outlet inside
  ハル's line, like （NHK, 2026-09-02）.
- **No crypto.** Rails covers stablecoins and regulation daily. A crypto story belongs here
  only when it is genuinely one of the biggest news items in Japan that day.

---

## Issue structure

Header: `JAPAN DAILY TALK — Issue #N`, the date line, a 2–3 sentence 今号のハイライト in
Japanese followed by the same in Korean, then `📖 登場人物:`.

**Four sections**, chosen by the day's news from this pool, **always including
テクノロジートーク**:

- `政治トーク (POLITICS TALK)`
- `経済トーク (ECONOMY TALK)`
- `テクノロジートーク (TECHNOLOGY TALK)` — AI, semiconductors, robotics, gadgets, platforms,
  telecoms, and the Japanese companies behind them. Same depth as politics, not an afterthought.
- `くらし・防災トーク (LIFESTYLE & SAFETY TALK)`
- `今日の話題 (TODAY'S BUZZ)` — may carry two stories

Each story:

```
【Japanese headline】(Korean translation of the headline)
ミン: [question]
민: [same line in Korean]
ハル: [the fact, the number, the source]
하루: [same line in Korean]
… six to eight dialogue lines, three or four turns each …
왜 중요한가: [1-2 Korean sentences on why it matters]
```

Then `SECTION 5 · 今日の日本語表現` — 📖 今日の表現 / 読み方 / 意味 / 例文 → Korean / 補足.
Pull the expression from a word that actually appeared earlier in the issue.

Closing: `Issue #N · 次号: <date>`, a one-line teaser in Japanese, then the same in Korean.

---

## Sources

`GOOGLE_NEWS_QUERIES` is the floor — 日本 政府 / 日本 経済 / 日本 AI / 日本 話題. The RSS feeds
(Yahoo トピックス ×5, 朝日新聞, ITmedia, GIGAZINE) are a bonus. There is **no keyword filter**:
every source is a Japanese domestic outlet, so filtering could only subtract.

NHK and Time Out Tokyo were removed — NHK's feed has been frozen since 2026-08-08 and
timeout.jp returns an HTTP error, so both were sitting in the list looking like coverage.

---

## Length

1,600–2,200 words total across both languages.

---

## Formatting rules (Calendar/Notion display)

- No Markdown at all
- `━━━━━━━━━━━━━━━━━━━━` as section dividers, before and after each SECTION line
- `【】` for story headlines, with the Korean translation in parentheses after
- `📖` only for the 登場人物 line and the expression of the day. No other emoji.
- Furigana toggles are added afterwards by `shared/furigana.py` — do **not** write readings in
  parentheses yourself, or they will be added twice.
