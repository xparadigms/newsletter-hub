# Japan Briefing — Bi-weekly Bilingual Newsletter

Automated bi-weekly newsletter that scrapes Japan crypto/regulation/real-estate news, generates a bilingual (日本語 body + 한국어 translation) issue via Claude, and saves it as a Google Calendar event + Notion page.

## How it works

1. **Scrape** — Pulls news from CoinPost, CoinDesk Japan, Nikkei Asia, NHK, The Block, Cointelegraph (RSS) + Telegram channels
2. **Filter** — Keeps articles relevant to Japan crypto regulation, stablecoins (JPYC, Progmat, megabanks), FIEA, real estate/urban development, KR-JP cross-border
3. **Generate** — Claude produces a bilingual issue following the format in `claude.md` (日本語本文 + 바로 아래 한국어 번역)
4. **Output** — Creates a Google Calendar event at 09:00 KST + a Notion page

Runs bi-weekly (every other Monday) at 08:00 KST via GitHub Actions.

## Newsletter format

Every section is written first in **Japanese** (natural, native-level business Japanese), then immediately followed by a **Korean translation** (casual-professional). The reader reads Japanese first for language practice, checks Korean if stuck.

### Sections
1. **日本クリプト・規制ウォッチ** — 2–3 Japan crypto/stablecoin/regulation stories
2. **不動産・都市開発** — 1–2 Tokyo redevelopment / urban planning stories
3. **今週の日本語表現** — One business Japanese expression from the news
4. **カルチャー・ひとくち** — One light culture item

## Setup

### 1. GitHub Secrets

Shared with `../finance-newsletter`:

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key (shared) |
| `GCP_SA_KEY` | Google Cloud service account JSON (shared) |
| `NOTION_TOKEN` | Notion integration token (shared) |

Japan Briefing–specific:

| Secret | Description |
|--------|-------------|
| `JAPAN_CALENDAR_ID` | Google Calendar ID for Japan Briefing |
| `JAPAN_NOTION_DATABASE_ID` | Notion database ID for Japan Briefing |

### 2. Run manually

```bash
export ANTHROPIC_API_KEY=your_key
export GCP_SA_KEY='{"type":"service_account",...}'
export CALENDAR_ID=your_calendar_id@group.calendar.google.com
export NOTION_TOKEN=your_notion_token
export NOTION_DATABASE_ID=your_notion_db_id
pip install -r requirements.txt
python main.py
```

## Architecture

Mirrors `../finance-newsletter` exactly — same scraper pattern, same Calendar/Notion output. Key differences:

- **RSS feeds**: Japan-specific (CoinPost, CoinDesk Japan, NHK, ITmedia, Nikkei Asia)
- **Keywords**: Japan crypto regulation + real estate (資金決済法, FIEA, 再開発, etc.)
- **Claude prompt**: Bilingual format (JP body + KR translation)
- **Schedule**: Bi-weekly instead of daily
- **Lookback**: 15 days instead of 36 hours
