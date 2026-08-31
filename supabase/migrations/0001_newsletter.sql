-- Newsletter Hub — Supabase becomes the primary datastore.
--
-- Apply by pasting this whole file into the Supabase SQL editor
-- (Dashboard → SQL Editor → New query → Run). There is one table, so the
-- Supabase CLI is not worth setting up; this file is the record of what was run.
--
-- Safe to re-run: it drops and recreates the table. Do NOT re-run once the
-- 318-issue backfill has landed.
--
-- Superseded in part by 0002_china.sql and 0003_mandarin.sql, which widen the
-- `section` and `source_format` checks. Do not derive the current schema from this file alone.

drop table if exists public.newsletter cascade;

create table public.newsletter (
  id             bigint generated always as identity primary key,

  section        text not null check (section in ('startup','fintech','japan','watch')),
  slug           text,                       -- filled by the trigger below; writers omit it
  issue_date     date not null,
  published_at   timestamptz not null default now(),

  title          text not null,              -- headline only, after parseTitle
  series         text,                       -- "Japan Daily Talk" etc., preserved as-drifted
  raw_title      text not null,              -- "[Series #N] (Headline)" verbatim
  issue_number   int,                        -- parsed out of raw_title; NOT unique
  summary        text,                       -- leading "- " already stripped

  blocks         jsonb not null,             -- the web's Block[] — what the site renders
  plain_text     text,                       -- flattened block text, for FTS and debugging
  source_text    text,                       -- raw generator output; new rows only
  source_format  text check (source_format in ('plain','trilingual_md')),

  notion_page_id text unique,                -- mirror linkage + backfill idempotency
  notion_url     text,
  run_key        text not null unique,       -- writer idempotency; see note below
  published      boolean not null default true,

  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),

  -- 'simple', not 'english': bodies are trilingual and English stemming would
  -- corrupt the JP/KO tokens. Unused by /api/search today, which filters
  -- ~318 titles client-side; this is here for body search later.
  fts tsvector generated always as (
    to_tsvector(
      'simple',
      coalesce(title, '') || ' ' || coalesce(series, '') || ' ' ||
      coalesce(summary, '') || ' ' || coalesce(plain_text, '')
    )
  ) stored,

  unique (section, slug)
);

comment on column public.newsletter.run_key is
  'Writer idempotency key. Generators write "{section}:{issue_date}"; the Notion '
  'backfill writes "notion:{page_id}". Neither (section, issue_date) nor '
  '(section, issue_number) is usable: startup''s day-by-day backfill produced '
  'same-day rows and every historical startup issue is titled #1. Kept as a '
  'plain unique column rather than a partial unique index because PostgREST''s '
  '?on_conflict= cannot express an index predicate.';

comment on column public.newsletter.published is
  'Doubles as the backfill staging flag: load rows false, verify, then flip.';

-- The only list query: one section, date-descending, ~130 rows.
create index newsletter_section_date_idx
  on public.newsletter (section, issue_date desc, published_at desc);

create index newsletter_fts_idx on public.newsletter using gin (fts);

-- (section, slug) lookups ride the unique constraint's index; no extra index.


-- ---------------------------------------------------------------------------
-- updated_at
-- ---------------------------------------------------------------------------

create or replace function public.touch_updated_at() returns trigger
  language plpgsql
  set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end
$$;

create trigger newsletter_touch
  before update on public.newsletter
  for each row execute function public.touch_updated_at();


-- ---------------------------------------------------------------------------
-- Slugs
--
-- Generated in SQL rather than in both Python and TypeScript, so the two
-- writers cannot drift and collision suffixing happens under the unique index
-- instead of racing it. Both writers omit `slug` and read the final value back
-- with `Prefer: return=representation`.
-- ---------------------------------------------------------------------------

create or replace function public.slugify(txt text) returns text
  language sql
  immutable
  set search_path = ''
as $$
  select nullif(
    trim(both '-' from regexp_replace(lower(coalesce(txt, '')), '[^a-z0-9]+', '-', 'g')),
    ''
  )
$$;

create or replace function public.newsletter_fill_slug() returns trigger
  language plpgsql
  set search_path = ''
as $$
declare
  base      text;
  candidate text;
  n         int := 1;
begin
  -- An explicitly supplied slug always wins.
  if new.slug is not null then
    return new;
  end if;

  -- Published URLs are permanent. A same-day rerun whose headline changed keeps
  -- the original slug, so the URL may not match the new title — that trade is
  -- deliberate: URL stability beats cosmetic accuracy.
  if tg_op = 'UPDATE' and old.slug is not null then
    new.slug := old.slug;
    return new;
  end if;

  base := to_char(new.issue_date, 'YYYY-MM-DD') || '-' ||
          coalesce(
            left(public.slugify(new.title), 60),
            -- A title with no Latin characters slugifies to NULL.
            'issue-' || coalesce(new.issue_number::text,
                                 extract(epoch from now())::bigint::text)
          );
  base := trim(both '-' from base);

  candidate := base;
  while exists (
    select 1
      from public.newsletter
     where section = new.section
       and slug = candidate
       and (tg_op = 'INSERT' or id <> new.id)
  ) loop
    n := n + 1;
    candidate := base || '-' || n;
  end loop;

  new.slug := candidate;
  return new;
end
$$;

create trigger newsletter_slug
  before insert or update on public.newsletter
  for each row execute function public.newsletter_fill_slug();


-- ---------------------------------------------------------------------------
-- Row level security
--
-- The web reads with the publishable (anon) key and sees only published rows.
-- The generators and the backfill write with the secret key, which bypasses RLS
-- entirely — so there is deliberately NO insert/update policy here. Adding one
-- would be the bug.
-- ---------------------------------------------------------------------------

alter table public.newsletter enable row level security;

-- Tables created from the SQL editor do not reliably inherit the dashboard's
-- default grants, so be explicit.
revoke all on public.newsletter from anon, authenticated;
grant select on public.newsletter to anon, authenticated;

create policy "read published"
  on public.newsletter
  for select
  to anon, authenticated
  using (published);
