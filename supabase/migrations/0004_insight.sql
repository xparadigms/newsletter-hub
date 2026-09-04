-- Business Insight joins the six existing sections.
--
-- Apply by pasting into the Supabase SQL editor. Additive and idempotent, like
-- 0002 and 0003: it never drops the table and is safe to re-run.
--
-- Daily business thinking from named operators, in Japanese with a full Korean
-- translation under every paragraph. It writes the same plain-text format the
-- Japanese newsletters do, so source_format needs no new value.

alter table public.newsletter
  drop constraint if exists newsletter_section_check;
alter table public.newsletter
  add constraint newsletter_section_check
  check (section in ('startup', 'fintech', 'japan', 'watch', 'china', 'mandarin', 'insight'));
