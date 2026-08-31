-- Mandarin Basics joins the five existing sections.
--
-- Apply by pasting into the Supabase SQL editor. Additive and idempotent, like
-- 0002: it never drops the table and is safe to re-run.
--
-- A study newsletter rather than a news one — a grammar point, new words in
-- context, and a short dialogue, at HSK 2-4. It writes the same marker format
-- China Daily does, so it shares shared/markers.py; the format value is named
-- for what it carries rather than for whichever newsletter wrote it.

alter table public.newsletter
  drop constraint if exists newsletter_section_check;
alter table public.newsletter
  add constraint newsletter_section_check
  check (section in ('startup', 'fintech', 'japan', 'watch', 'china', 'mandarin'));

alter table public.newsletter
  drop constraint if exists newsletter_source_format_check;
alter table public.newsletter
  add constraint newsletter_source_format_check
  check (source_format in ('plain', 'trilingual_md', 'china_md', 'lesson_md'));
