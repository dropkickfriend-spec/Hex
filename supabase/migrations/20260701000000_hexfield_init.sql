-- HEXFIELD Supabase schema
-- Tables the static app (docs/index.html) reads/writes via sbClient().
-- Public art toy: no PII. Anonymous visitors may read + append (and update the
-- evolutionary score on logo_seeds). Row-level security is ON; policies below
-- grant exactly SELECT/INSERT (+ UPDATE on logo_seeds) to the anon role.

-- ── logo_seeds ──────────────────────────────────────────────────────────────
-- Global no-repeat + evolutionary "memory" for the billiard logo generator.
create table if not exists public.logo_seeds (
  seed        bigint primary key,          -- mulberry32 hash; natural unique key
  generation  integer      default 1,
  font        text,
  rule        text,
  hue         integer,
  letters     text,
  coverage    integer      default 0,
  expanded    boolean      default false,
  score       numeric      default 0,
  ts          timestamptz  default now()
);
create index if not exists logo_seeds_generation_idx on public.logo_seeds (generation desc, ts desc);

-- ── hex_sim_states ──────────────────────────────────────────────────────────
-- Reaction-diffusion background states, deduped by hash.
create table if not exists public.hex_sim_states (
  id           bigint generated always as identity primary key,
  hash         text unique,
  f_param      numeric,
  k_param      numeric,
  palette_hue  numeric,
  ts           timestamptz default now()
);

-- ── logo_library ────────────────────────────────────────────────────────────
-- Saved logo picks (the "library" strip in the Logo tool).
create table if not exists public.logo_library (
  id          bigint generated always as identity primary key,
  font        text,
  rule        text,
  hue_off     numeric,
  brand_name  text,
  category    text,
  coverage    integer,
  expanded    boolean,
  ts          timestamptz default now()
);
create index if not exists logo_library_ts_idx on public.logo_library (ts desc);

-- ── billiards_trails ────────────────────────────────────────────────────────
-- Optional telemetry of ball trails per tick.
create table if not exists public.billiards_trails (
  id         bigint generated always as identity primary key,
  tick       integer,
  points     jsonb,
  coverage   integer,
  expanded   boolean,
  ts         timestamptz default now()
);

-- ── Row-level security ──────────────────────────────────────────────────────
alter table public.logo_seeds       enable row level security;
alter table public.hex_sim_states   enable row level security;
alter table public.logo_library     enable row level security;
alter table public.billiards_trails enable row level security;

-- anon (and signed-in) visitors: read + append everywhere; update only the
-- evolutionary score fields on logo_seeds. No deletes.
do $$
declare t text;
begin
  foreach t in array array['logo_seeds','hex_sim_states','logo_library','billiards_trails']
  loop
    execute format('drop policy if exists %I on public.%I', t||'_sel', t);
    execute format('drop policy if exists %I on public.%I', t||'_ins', t);
    execute format('create policy %I on public.%I for select to anon, authenticated using (true)', t||'_sel', t);
    execute format('create policy %I on public.%I for insert to anon, authenticated with check (true)', t||'_ins', t);
  end loop;
  drop policy if exists logo_seeds_upd on public.logo_seeds;
  create policy logo_seeds_upd on public.logo_seeds for update to anon, authenticated using (true) with check (true);
end $$;

-- ── Grants (explicit, so raw-SQL migrations work regardless of defaults) ─────
grant usage on schema public to anon, authenticated;
grant select, insert on public.logo_seeds, public.hex_sim_states, public.logo_library, public.billiards_trails to anon, authenticated;
grant update on public.logo_seeds to anon, authenticated;
grant usage, select on all sequences in schema public to anon, authenticated;
