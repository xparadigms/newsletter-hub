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
four databases.

`REVALIDATE_SECRET` is optional and guards `POST /api/revalidate`; the route
returns 401 for every request when it isn't set.

## Caching

Lists (the homepage, section indexes, search) revalidate every 5 minutes.

Issue bodies don't expire at all. Assembling one costs ~45 Notion calls and a
few seconds, and a published issue doesn't change, so a timer only ever bought
the same content back at full price — which is what made archive issues and
deep links slow. They're evicted on demand instead:

```bash
# every issue, plus the lists
curl -X POST "$SITE/api/revalidate" -H "authorization: Bearer $REVALIDATE_SECRET"

# just one issue
curl -X POST "$SITE/api/revalidate" \
  -H "authorization: Bearer $REVALIDATE_SECRET" \
  -H 'content-type: application/json' \
  -d '{"id":"<notion-page-id>"}'
```

Run this after editing an issue that's already published. New issues appear on
their own once the lists refresh.

## Data mapping (`lib/notion.ts`)

- `Name` (title) → headline; the `[Series #N] (Headline)` prefix is split into
  a series tag
- `Date` → publish date (sorted descending)
- `Summary` (rich text, where present) → list/deck summary
- Page blocks → paragraphs, headings, lists, quotes, code, images, dividers,
  callouts, and toggles (children fetched one level deep)
