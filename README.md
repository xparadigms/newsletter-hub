# The Brief

A newsletter site backed by four Notion databases, styled after
[tempo.xyz](https://tempo.xyz/) — white background, grayscale hairlines,
emerald accent, numbered sections, and a sans / serif / mono type mix.

## Sections

- **01 / Startup** — Startup Newsletter (funding, M&A, launches)
- **02 / Fintech** — Finance Infra daily journal
- **03 / Japan** — Japan Brief on the digital asset market
- **04 / Watch** — Watch Weekly

Each section maps to one Notion database (`lib/config.ts`). The homepage shows
the latest five entries per section; each section has a full index page and
every entry has a detail page rendered from Notion blocks — including callouts
(Japanese translations) and collapsible toggles (furigana).

## Running

```bash
npm install
cp .env.example .env.local   # then set NOTION_TOKEN
npm run dev
```

`NOTION_TOKEN` is an internal-integration token that has been shared with all
four databases. Content revalidates every 5 minutes in production.

## Data mapping (`lib/notion.ts`)

- `Name` (title) → headline; the `[Series #N] (Headline)` prefix is split into
  a series tag
- `Date` → publish date (sorted descending)
- `Summary` (rich text, where present) → list/deck summary
- Page blocks → paragraphs, headings, lists, quotes, code, images, dividers,
  callouts, and toggles (children fetched one level deep)
