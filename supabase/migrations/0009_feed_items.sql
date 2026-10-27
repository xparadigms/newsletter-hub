-- The hourly news feed: headlines from each newsletter's sources, collected by
-- shared/news_feed.py (news-feed.yml) and shown in the Feed tab. Readers can
-- only read; the job writes with the secret key, which bypasses RLS.
-- Applied in the SQL editor on 2026-10-27.
create table if not exists public.feed_items (
  id bigint generated always as identity primary key,
  section text not null,
  url text not null unique,
  title text not null,
  source text,
  summary text,
  image_url text,
  published_at timestamptz,
  fetched_at timestamptz not null default now()
);
create index if not exists feed_items_section_published on public.feed_items (section, published_at desc);
alter table public.feed_items enable row level security;
grant select on public.feed_items to anon, authenticated;
create policy read_feed on public.feed_items for select using (true);
