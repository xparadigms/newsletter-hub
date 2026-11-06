-- Phones to notify when an issue is published (shared/push.py). The app can
-- only add or update its own token, through register_device; the table is not
-- readable with the publishable key. Applied in the SQL editor on 2026-11-06.
create table if not exists public.push_devices (
  token text primary key,
  mode text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.push_devices enable row level security;
create or replace function public.register_device(p_token text, p_mode text) returns void
language sql security definer set search_path = public as $$
  insert into public.push_devices (token, mode) values (p_token, p_mode)
  on conflict (token) do update set mode = excluded.mode, updated_at = now();
$$;
grant execute on function public.register_device(text, text) to anon;
