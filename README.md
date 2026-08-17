# Newsletter Hub

Monorepo for four automated newsletters and the site that publishes them. Each
newsletter generates an issue with Anthropic Claude, writes it to a Notion
database, and adds a Google Calendar event. `web/` reads those same Notion
databases back out and renders them as a website.

Consolidated from five separate repositories: `finance-newsletter`,
`japan-newsletter`, `startup-techcrunch-summary`, `watch-newsletter`, and
`japan-newsletter-web`. Every project's full commit history is preserved.

### Reading pre-migration history

Finance was moved with `git mv`, so ordinary rename following works:

```bash
git log --follow -- finance-newsletter/main.py
```

Japan, Startup, Watch, and the web app were brought in with `git subtree`, which
attaches their history through a merge commit. `--follow` does **not** traverse
merges, so it reports nothing for those paths. Reach their original commits
through the merge commit's second parent instead:

```bash
# list a project's pre-migration commits
git log --oneline "$(git log --format=%H --grep='Merge japan-newsletter into monorepo' -1)^2"
```

The original commit SHAs are unchanged, so `git show <old-sha>` also still works
directly.

## Projects

| Directory | Newsletter | Schedule (UTC) | Status |
| --- | --- | --- | --- |
| `finance-newsletter/` | Rails — financial infrastructure | 23:00 daily | Active |
| `startup-newsletter/` | Startup News summary | 23:20 daily | Active |
| `watch-newsletter/` | Watch Weekly | 00:00 Saturday | Active |
| `japan-newsletter/` | Japan Briefing | — | **Paused** |

Daily jobs are staggered so the API-heavy runs do not hit Anthropic and Notion
simultaneously.

Japan is paused deliberately: its `schedule` trigger in
`.github/workflows/japan-daily.yml` is commented out. Uncomment the two
`schedule` lines to resume it.

## The site (`web/`)

`web/` is "The Brief", a Next.js app that renders all four newsletters from
their Notion databases — one numbered section each for Startup, Fintech, Japan,
and Watch (`web/lib/config.ts`). It came from the `japan-newsletter-web`
repository but is not Japan-specific, which is why it sits at `web/` rather than
next to the generators. See `web/README.md` for its caching and data model.

### Deploying

The site is the Vercel project `heechang-newsletter`, serving
<https://japan-newsletter.vercel.app>. It has no GitHub Actions workflow and no
Vercel Git integration — pushing to `main` deploys nothing. Deploys are pushed
by hand with the Vercel CLI, from inside `web/`:

```bash
cd web
vercel deploy          # preview build; preview URLs are SSO-protected
vercel deploy --prod   # production, re-aliases japan-newsletter.vercel.app
```

Because the CLI treats the directory you run it from as the project root,
`web/` is the correct place to run it and no Root Directory setting is
involved. The link lives in `web/.vercel/`, which is gitignored, so a fresh
clone runs `vercel link --project heechang-newsletter` once first.

`NOTION_TOKEN` is set on the Vercel project for both production and preview;
`REVALIDATE_SECRET` is not set, so `POST /api/revalidate` currently answers 401
to everything.

## Layout

Workflows live in the root `.github/workflows/` because GitHub only reads
workflow files from the repository root. Each workflow sets
`defaults.run.working-directory` to its project directory and installs from the
shared root `requirements.txt`.

```
.github/workflows/
  daily-newsletter.yml   # finance-newsletter
  backfill.yml           # finance-newsletter, manual recovery
  japan-daily.yml        # japan-newsletter (paused)
  startup-daily.yml      # startup-newsletter
  watch-weekly.yml       # watch-newsletter
requirements.txt         # shared dependency union
<project>/main.py        # each newsletter's entry point
web/                     # Next.js site, deployed with the Vercel CLI
```

The site keeps its own `package.json` and `tsconfig.json` inside `web/`; the
root `.gitignore` covers both the Python and the Node build artefacts.

## Issue numbering

Each newsletter titles its issues `[Name #N]`, where `N` comes from
`ISSUE_NUMBER`. This is derived from `github.run_number`, which GitHub scopes
**per workflow file** — a new workflow file starts counting at 1.

`finance-newsletter` kept its original workflow filename during the migration,
so its counter continues uninterrupted. The other three workflows are new files
and therefore add an `ISSUE_NUMBER_OFFSET` equal to the run count their old repo
reached:

- `japan-daily.yml` — offset 45
- `watch-weekly.yml` — offset 6
- `startup-daily.yml` — offset 163

Startup previously never passed `ISSUE_NUMBER` at all, so every issue was titled
`[Startup News #1]`; the offset fixes that as well.

If you ever rename a workflow file, add its current run count to that
workflow's offset, or issue numbers will restart from 1.

## Secrets

Configured as repository secrets:

- `ANTHROPIC_API_KEY`
- `GCP_SA_KEY` — Google service-account JSON for Calendar
- `NOTION_TOKEN`

Notion database IDs and the shared calendar ID are non-sensitive and are set
directly in each workflow.

The site does not use these repository secrets; its own environment lives on
the Vercel project instead — see "Deploying" above.

## Local development

Each project reads its own untracked env file (`.env`, or `.env.local` for
Japan). The root `.gitignore` ignores every `.env` variant and stray credential
JSON, so these are never committed.

```bash
pip install -r requirements.txt
cd finance-newsletter
python main.py
```

Note that running a project locally writes to the real Notion database and
calendar. The site only reads, so it is safe to run:

```bash
cd web
npm install
npm run dev            # needs NOTION_TOKEN in web/.env.local
```

## Recovering a failed run

If a run creates the calendar event but fails before saving to Notion, the issue
text survives only in the event description. The Finance project can recover it:

```bash
gh workflow run backfill.yml -f issue_number=<N> -f commit=false  # dry run
gh workflow run backfill.yml -f issue_number=<N> -f commit=true   # write
```

It refuses to create a page that already exists, so it cannot double-post.

Finance writes to Notion *before* creating the calendar event, so a Notion
failure aborts before any external side effect exists. The other three projects
still create the calendar event first.
