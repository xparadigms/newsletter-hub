-- China Daily joins the four existing sections, and brings its own source format.
--
-- Apply by pasting into the Supabase SQL editor (Dashboard → SQL Editor → Run).
--
-- Unlike 0001, this file is additive and idempotent: it never drops the table
-- and is safe to re-run against the migrated archive. Inline column checks in
-- 0001 were unnamed, so Postgres auto-named them "{table}_{column}_check".
--
-- china is Supabase-only: no Notion database, no Notion mirror, no calendar
-- event. It is the first section to depend on Supabase being the datastore
-- rather than a copy of one.

alter table public.newsletter
  drop constraint if exists newsletter_section_check;
alter table public.newsletter
  add constraint newsletter_section_check
  check (section in ('startup', 'fintech', 'japan', 'watch', 'china'));

-- 'china_md': the marker-delimited format the China generator emits — a Korean
-- heading per story, Chinese sentence lines, and one Korean translation line.
-- Its blocks are built natively rather than mapped from Notion blocks, so the
-- source text is the only way back to what Claude actually returned.
alter table public.newsletter
  drop constraint if exists newsletter_source_format_check;
alter table public.newsletter
  add constraint newsletter_source_format_check
  check (source_format in ('plain', 'trilingual_md', 'china_md'));
