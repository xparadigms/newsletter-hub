# Japan Briefing — Newsletter Agent Guide

## What this is

A bi-weekly automated newsletter that scrapes Japanese-language news on crypto regulation, stablecoins, and real estate/urban development, then generates a bilingual briefing (日本語 body + 한국어 translation below each section) via Claude and saves it to Google Calendar + Notion.

The target reader is Heechang — a Korean crypto professional studying Japanese, with active interest in Japan's stablecoin/FIEA regulatory landscape and Tokyo real estate trends. The newsletter serves dual purposes: **business intelligence** (Japan crypto infra, regulation) and **Japanese language learning** (reading real industry articles in Japanese with Korean fallback).

---

## Architecture (mirrors `../finance-newsletter`)

```
japan-newsletter/
├── claude.md          # Full prompt spec for Claude (voice, structure, bilingual format)
├── main.py            # Scraper + Claude generation + Calendar/Notion output
├── requirements.txt   # Python dependencies (same as finance-newsletter)
├── .env.local         # References to ../finance-newsletter env vars
├── .gitignore
└── .github/
    └── workflows/
        └── daily.yml  # GitHub Actions (bi-weekly schedule)
```

### Shared infrastructure with `../finance-newsletter`
- Same Google Calendar service account (`GCP_SA_KEY`)
- Same Anthropic API key (`ANTHROPIC_API_KEY`)
- Same Notion integration (`NOTION_TOKEN`)
- **Different** Calendar ID and Notion database ID (set in workflow env)

---

## Newsletter format: 日本語本文 + 한국어번역

Every content section follows this bilingual pattern:

```
[Japanese body — the primary content, written in natural Japanese]

[한국어 번역 — Korean translation immediately below]
```

The reader reads the Japanese first for language practice, then checks the Korean translation if stuck. This is the core UX — **sequential** (JP first, KR below), not side-by-side.

---

## Content sections

### Section 1: 日本クリプト・規制ウォッチ (Japan Crypto & Regulation Watch)
- 2–3 stories from the last 2 weeks on Japan stablecoin, FIEA, JVCEA, FSA, megabank, crypto regulatory developments
- Sources: Nikkei, CoinPost, CoinDesk Japan, The Block, FSA press releases, JPYC/Progmat announcements
- Each story: headline (JP) → 3–4 sentence summary (JP) → Korean translation below
- Tie back to Heechang's ASA/ASC 2026 work and Asia stablecoin corridor research

### Section 2: 不動産・都市開発 (Real Estate & Urban Development)
- 1–2 stories on Tokyo redevelopment, zoning changes, major projects, or JP vs KR urban planning comparisons
- Sources: Nikkei, Suumo Journal, Tokyo Metropolitan Government
- "Seoul's 10 years from now" angle — what Tokyo's private-led redevelopment tells us about Korean 정비사업

### Section 3: 今週の日本語表現 (Japanese Expression of the Week)
- One business/economic Japanese expression pulled from the actual news articles
- Format: expression (JP) → reading (furigana) → meaning (KR) → example sentence (JP+KR)
- Prioritize terms useful for panel moderating, professional conversation

### Section 4: カルチャー・ひとくち (Culture Bite)
- One light item: Japanese media trend, lifestyle/wellness, gadget, or K-pop/J-pop crossover
- 3–4 sentences max. Palate cleanser.

### Closing
- Issue number, next issue date, one-line teaser

---

## Tone & voice

- **Bilingual**: Japanese body is the default. Korean translation follows every substantive block.
- **Japanese level**: Natural, native-level business Japanese. Not textbook-simplified. Reader is N3–N2 level learning through immersion.
- **Korean tone**: Casual-professional (반말 fine). Like explaining to a colleague.
- **Analytical**: Connect crypto/regulation coverage to ASA, ASC 2026, Four Pillars research. Not generic news roundup.
- **No filler**: Skip sections if signal is thin. Shorter and sharper beats padding.

---

## Cadence

**Bi-weekly** (every other Monday, KST).

---

## Source diet (Japanese-language priority)

### Crypto / Regulation
- CoinPost (コインポスト): https://coinpost.jp/
- CoinDesk Japan: https://www.coindeskjapan.com/
- Nikkei (金融): https://www.nikkei.com/
- FSA press releases: https://www.fsa.go.jp/
- JPYC blog / Progmat blog
- The Block / DL News (Japan-specific stories)

### Real Estate / Urban Development
- Nikkei: https://www.nikkei.com/
- Suumo Journal: https://suumo.jp/journal/
- Tokyo Metropolitan Government: https://www.metro.tokyo.lg.jp/

### Culture
- NHK News Web: https://www3.nhk.or.jp/news/
- ITmedia: https://www.itmedia.co.jp/

---

## Technical notes

1. **main.py** adapted from `../finance-newsletter/main.py` — same architecture (RSS + Telegram), same Calendar/Notion output, Japan-specific RSS feeds and keywords
2. **claude.md** is the full prompt spec — adapted from `../finance-newsletter/claude.md` with bilingual format and Japan-focused sections
3. **Environment variables**: reuse secrets from `../finance-newsletter` (ANTHROPIC_API_KEY, GCP_SA_KEY, NOTION_TOKEN) with different CALENDAR_ID and NOTION_DATABASE_ID
4. **GitHub Actions**: bi-weekly cron instead of daily
5. `.env.local` references that API keys live in `../finance-newsletter/.env` or GitHub Secrets
