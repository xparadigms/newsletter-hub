-- Business Insight is renamed from 'insight' to 'business', and moves in the
-- running order to sit next to Startup.
--
-- Apply by pasting into the Supabase SQL editor. Safe to re-run: the update
-- matches nothing once it has run, and both constraint statements are
-- drop-then-add.
--
-- The rows are migrated inside the same script, between dropping the old
-- constraint and adding the new one — 'insight' is not in the new check, so
-- the update has to happen while no constraint is in force.

alter table public.newsletter
  drop constraint if exists newsletter_section_check;

update public.newsletter set section = 'business' where section = 'insight';

alter table public.newsletter
  add constraint newsletter_section_check
  check (section in ('startup', 'fintech', 'japan', 'watch', 'china', 'mandarin', 'business'));
