-- Podcast Hub joins as section 'podcasts': one article per podcast episode,
-- written by podcasts-newsletter/main.py (podcasts.yml).
--
-- Apply by pasting into the Supabase SQL editor. Safe to re-run: the
-- constraint is drop-then-add.
--
-- Each episode is its own row. Its run_key is podcasts:<episode date>:p<show>-<id>,
-- so nothing else in the schema has to change.
--
-- Applied 2026-11-08 as the drop alone (shared/issue.py checks section names
-- before every write); the add below restores the database-side check.

alter table public.newsletter
  drop constraint if exists newsletter_section_check;

alter table public.newsletter
  add constraint newsletter_section_check
  check (section in ('startup', 'fintech', 'japan', 'watch', 'china', 'mandarin', 'business', 'stocks', 'podcasts'));
