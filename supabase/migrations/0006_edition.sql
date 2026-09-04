-- A day can hold more than one issue per section.
--
-- Apply by pasting into the Supabase SQL editor. Additive and idempotent.
--
-- The table never keyed on (section, issue_date) — idempotency has always run
-- through run_key, and the slug trigger already suffixes collisions — so an
-- extra issue needs only a distinct run_key. This column exists to make the
-- concept explicit rather than implied by a key format: the site can label an
-- edition, and the generate endpoint can count today's.

alter table public.newsletter
  add column if not exists edition int not null default 1;

comment on column public.newsletter.edition is
  'Which issue of the day this is. 1 for the scheduled run; 2+ for issues made '
  'on demand from the site, whose run_key carries a matching ":e{n}" suffix.';

-- Counting today's editions for the rate limit, and listing a section in order.
create index if not exists newsletter_section_date_edition_idx
  on public.newsletter (section, issue_date desc, edition desc);
