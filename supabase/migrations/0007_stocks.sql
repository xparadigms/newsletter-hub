-- Three Companies (the daily stock newsletter) joins as section 'stocks'.
--
-- Apply by pasting into the Supabase SQL editor. Safe to re-run: the
-- constraint is drop-then-add.
--
-- It publishes three articles per day, one per company. Nothing else in the
-- schema has to change for that: run_key already carries the uniqueness, and
-- the generator suffixes it with ":p1", ":p2", ":p3".

alter table public.newsletter
  drop constraint if exists newsletter_section_check;

alter table public.newsletter
  add constraint newsletter_section_check
  check (section in ('startup', 'fintech', 'japan', 'watch', 'china', 'mandarin', 'business', 'stocks'));
