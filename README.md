# Watch Weekly — Trilingual Newsletter

A weekly horology/watch-industry newsletter. It pulls the past week of watch news
from watch-media RSS feeds, writes an AI weekly recap, converts it to a trilingual
(English + Japanese + Korean) edition, and publishes to:

- **Google Calendar** — one event at 09:00 KST with the trilingual text as the
  (plain-text) event description.
- **Notion** — a rich page (furigana toggles + Korean callouts) in the target database.

Format mirrors `../startup-newsletter`; the source is watch RSS instead of Telegram.

## Pipeline (`main.py`)

1. `scrape_rss_feeds()` — recent entries from Hodinkee, Fratello, Monochrome,
   aBlogtoWatch, WatchPro, SJX, Worn & Wound, Time+Tide, Quill & Pad, Revolution.
2. `generate_summary()` — Claude writes the weekly English briefing.
3. `generate_trilingual()` — Claude converts it to EN/JP/KR Notion-flavored Markdown.
4. `create_calendar_event()` — trilingual plain-text description on the shared calendar.
5. `create_notion_page()` — rich trilingual page; the title/date properties are
   auto-discovered from the database schema.

## Run locally

```bash
pip install -r requirements.txt
# .env must define ANTHROPIC_API_KEY, NOTION_TOKEN, GCP_SA_KEY (+ optional
# CALENDAR_ID, NOTION_DATABASE_ID, TIMEZONE); see ../startup-newsletter/.env
python main.py
```

Set `ISSUE_NUMBER` to control the issue number (defaults to 1 locally; the workflow
uses the GitHub run number).

## Weekly schedule

`.github/workflows/weekly.yml` runs every **Saturday 00:00 UTC (09:00 KST)** and can
also be triggered manually (`workflow_dispatch`). For it to run on GitHub, push this
repo and add repo secrets: `ANTHROPIC_API_KEY`, `NOTION_TOKEN`, `GCP_SA_KEY`.
`CALENDAR_ID` and `NOTION_DATABASE_ID` are set inline in the workflow.

## Config

- **Notion database:** `3965bc953df381bbb5ece93744153a6a` (override with `NOTION_DATABASE_ID`).
  The Notion integration behind `NOTION_TOKEN` must be shared to this database.
- **Calendar:** shared Google Calendar (same as the other newsletters).
- **Sources:** edit `RSS_FEEDS` in `main.py` to add/remove watch outlets.

---
*Draft built with assistance from Oz (Warp).*
