-- A cover image per issue: {"url", "credit", "link", "kind"}, filled by
-- shared/covers.py as each issue is stored, and for the archive by
-- shared/backfill_covers.py. Applied in the SQL editor on 2026-10-25.
alter table public.newsletter add column if not exists cover jsonb;
