-- Black Card Protocol – Nürnberg Creator & Partner Network
-- Vollständiges Schema (Tabellen, Trigger, RPCs, RLS). Im Supabase SQL-Editor ausführen.

create extension if not exists pgcrypto;

-- ───────────── Tabellen ─────────────
create table if not exists public.profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  role        text not null default 'influencer' check (role in ('admin','partner','influencer')),
  name        text,
  trust_score int  not null default 50 check (trust_score between 0 and 100),
  is_banned   boolean not null default false,
  created_at  timestamptz not null default now()
);

create table if not exists public.partners (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  owner_id   uuid references public.profiles(id) on delete set null,
  active     boolean not null default false,            -- false = wartet auf Freigabe
  type       text not null default 'cafe' check (type in ('cafe','restaurant','bar','lounge','bakery','other')),
  address    text,
  lat        double precision,
  lng        double precision,
  offer      text not null default 'Gratis Getränk',
  created_at timestamptz not null default now()
);

create table if not exists public.creator_passes (
  id             uuid primary key default gen_random_uuid(),
  influencer_id  uuid not null unique references public.profiles(id) on delete cascade,
  pass_token     uuid not null unique default gen_random_uuid(),
  status         text not null default 'active' check (status in ('active','locked','revoked')),
  cooldown_until timestamptz
);

create table if not exists public.redemptions (
  id            uuid primary key default gen_random_uuid(),
  partner_id    uuid not null references public.partners(id) on delete cascade,
  influencer_id uuid not null references public.profiles(id) on delete cascade,
  status        text not null default 'pending' check (status in ('pending','story_submitted','verified','flagged')),
  story_url     text,
  redeemed_at   timestamptz not null default now()
);

create table if not exists public.app_settings (
  key   text primary key,
  value text not null
);
insert into public.app_settings (key, value) values
  ('cooldown_days',   '7'),   -- Wartezeit zwischen zwei Einlösungen
  ('min_trust_score', '20'),  -- darunter keine Einlösung mehr
  ('trust_verified',  '3'),   -- Trust-Bonus bei geprüfter Story
  ('trust_flagged',   '15')   -- Trust-Abzug bei Betrug
on conflict (key) do nothing;

create index if not exists redemptions_partner_idx    on public.redemptions(partner_id, redeemed_at desc);
create index if not exists redemptions_influencer_idx on public.redemptions(influencer_id, redeemed_at desc);
create index if not exists partners_owner_idx         on public.partners(owner_id);

-- ───────────── Hilfsfunktionen ─────────────
create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles where id = auth.uid() and role = 'admin');
$$;

create or replace function public.setting_int(k text, d int) returns int
language sql stable security definer set search_path = public as $$
  select coalesce((select value::int from public.app_settings where key = k), d);
$$;

-- Neuer Auth-User → Profil. account_type 'partner' → Rolle partner + Betrieb (wartet auf Freigabe).
-- Alles andere → influencer + Pass. 'admin' kann nie über Registrierung entstehen.
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  m jsonb := coalesce(new.raw_user_meta_data, '{}'::jsonb);
  v_name text := coalesce(nullif(m->>'name',''), split_part(new.email, '@', 1));
  v_type text := coalesce(nullif(m->>'business_type',''), 'cafe');
begin
  if m->>'account_type' = 'partner' then
    insert into public.profiles (id, role, name) values (new.id, 'partner', v_name);
    if v_type not in ('cafe','restaurant','bar','lounge','bakery','other') then v_type := 'other'; end if;
    insert into public.partners (name, owner_id, active, type, address, offer)
    values (coalesce(nullif(m->>'business_name',''), v_name), new.id, false, v_type,
            nullif(m->>'address',''), coalesce(nullif(m->>'offer',''), 'Gratis Getränk'));
  else
    insert into public.profiles (id, role, name) values (new.id, 'influencer', v_name);
    insert into public.creator_passes (influencer_id) values (new.id);
  end if;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- Rolle wechselt zu 'influencer' → Pass sicherstellen
create or replace function public.ensure_pass() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.role = 'influencer' then
    insert into public.creator_passes (influencer_id) values (new.id) on conflict do nothing;
  end if;
  return new;
end $$;
drop trigger if exists ensure_pass on public.profiles;
create trigger ensure_pass after update of role on public.profiles
  for each row when (old.role is distinct from new.role) execute function public.ensure_pass();

-- Nutzer dürfen nur ihren Namen ändern; role/trust_score/is_banned nur Admins
create or replace function public.guard_profile_update() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if not public.is_admin() and auth.uid() is not null and
     (new.role is distinct from old.role or new.trust_score is distinct from old.trust_score
      or new.is_banned is distinct from old.is_banned or new.id is distinct from old.id) then
    raise exception 'Nur Admins dürfen role, trust_score oder is_banned ändern';
  end if;
  return new;
end $$;
drop trigger if exists guard_profile_update on public.profiles;
create trigger guard_profile_update before update on public.profiles
  for each row execute function public.guard_profile_update();

-- Partner dürfen Stammdaten ändern, aber weder active noch owner_id
create or replace function public.guard_partner_update() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if not public.is_admin() and auth.uid() is not null and
     (new.active is distinct from old.active or new.owner_id is distinct from old.owner_id) then
    raise exception 'Nur Admins dürfen active oder owner_id ändern';
  end if;
  return new;
end $$;
drop trigger if exists guard_partner_update on public.partners;
create trigger guard_partner_update before update on public.partners
  for each row execute function public.guard_partner_update();

-- ───────────── RPC: Scan / Einlösung ─────────────
create or replace function public.redeem_pass(p_token uuid, p_partner_id uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  v_pass public.creator_passes;
  v_prof public.profiles;
begin
  if not exists (select 1 from public.partners
                 where id = p_partner_id and active
                   and (owner_id = auth.uid() or public.is_admin())) then
    return jsonb_build_object('ok', false, 'reason', 'Partner nicht berechtigt oder nicht freigegeben');
  end if;

  select * into v_pass from public.creator_passes where pass_token = p_token for update;
  if not found then
    return jsonb_build_object('ok', false, 'reason', 'Pass existiert nicht');
  end if;

  select * into v_prof from public.profiles where id = v_pass.influencer_id;
  if v_prof.is_banned then
    return jsonb_build_object('ok', false, 'reason', 'Creator ist gesperrt', 'name', v_prof.name);
  end if;
  if v_prof.trust_score < public.setting_int('min_trust_score', 20) then
    return jsonb_build_object('ok', false, 'reason', 'Trust-Score zu niedrig', 'name', v_prof.name);
  end if;
  if v_pass.status = 'revoked' then
    return jsonb_build_object('ok', false, 'reason', 'Pass wurde widerrufen', 'name', v_prof.name);
  end if;
  if v_pass.status = 'locked' then
    return jsonb_build_object('ok', false, 'reason', 'Pass gesperrt – Story-Link fehlt', 'name', v_prof.name);
  end if;
  if v_pass.cooldown_until is not null and v_pass.cooldown_until > now() then
    return jsonb_build_object('ok', false, 'reason', 'Cooldown aktiv', 'name', v_prof.name,
                              'cooldown_until', v_pass.cooldown_until);
  end if;

  insert into public.redemptions (partner_id, influencer_id) values (p_partner_id, v_pass.influencer_id);
  update public.creator_passes
     set status = 'locked',
         cooldown_until = now() + make_interval(days => public.setting_int('cooldown_days', 7))
   where id = v_pass.id;

  return jsonb_build_object('ok', true, 'name', v_prof.name, 'trust_score', v_prof.trust_score,
                            'offer', (select offer from public.partners where id = p_partner_id));
end $$;

-- ───────────── RPC: Story-Link einreichen ─────────────
create or replace function public.submit_story(p_url text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_id uuid;
begin
  if auth.uid() is null then
    return jsonb_build_object('ok', false, 'reason', 'Nicht eingeloggt');
  end if;
  if p_url !~* '^https://([a-z0-9-]+\.)*(instagram\.com|tiktok\.com|facebook\.com|youtube\.com|youtu\.be)/\S+$' then
    return jsonb_build_object('ok', false, 'reason', 'Ungültiger Story-Link');
  end if;
  if exists (select 1 from public.redemptions where story_url = p_url) then
    return jsonb_build_object('ok', false, 'reason', 'Dieser Link wurde bereits verwendet');
  end if;

  select id into v_id from public.redemptions
   where influencer_id = auth.uid() and status = 'pending'
   order by redeemed_at desc limit 1 for update;
  if v_id is null then
    return jsonb_build_object('ok', false, 'reason', 'Keine offene Einlösung');
  end if;

  update public.redemptions set story_url = p_url, status = 'story_submitted' where id = v_id;
  update public.creator_passes set status = 'active'
   where influencer_id = auth.uid() and status = 'locked';
  return jsonb_build_object('ok', true);
end $$;

-- ───────────── RPC: Admin prüft Story ─────────────
create or replace function public.review_redemption(p_id uuid, p_verdict text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare r public.redemptions;
begin
  if not public.is_admin() then
    return jsonb_build_object('ok', false, 'reason', 'Nur Admins');
  end if;
  if p_verdict not in ('verified','flagged') then
    return jsonb_build_object('ok', false, 'reason', 'Ungültiges Urteil');
  end if;
  select * into r from public.redemptions where id = p_id for update;
  if not found then return jsonb_build_object('ok', false, 'reason', 'Nicht gefunden'); end if;
  if r.status = p_verdict then return jsonb_build_object('ok', true); end if;

  update public.redemptions set status = p_verdict where id = p_id;
  if p_verdict = 'verified' then
    update public.profiles set trust_score = least(100, trust_score + public.setting_int('trust_verified', 3)) where id = r.influencer_id;
  else
    update public.profiles set trust_score = greatest(0, trust_score - public.setting_int('trust_flagged', 15)) where id = r.influencer_id;
  end if;
  return jsonb_build_object('ok', true);
end $$;

-- ───────────── RPC: Scan-Historie für Partner (ohne Zugriff auf fremde Profile) ─────────────
create or replace function public.partner_scans(p_partner_id uuid, p_limit int default 30)
returns table (id uuid, creator_name text, status text, redeemed_at timestamptz)
language sql stable security definer set search_path = public as $$
  select r.id, p.name, r.status, r.redeemed_at
    from public.redemptions r join public.profiles p on p.id = r.influencer_id
   where r.partner_id = p_partner_id
     and exists (select 1 from public.partners x where x.id = p_partner_id and (x.owner_id = auth.uid() or public.is_admin()))
   order by r.redeemed_at desc limit least(p_limit, 200);
$$;

-- ───────────── RPC: öffentliche Partnerliste (Landingpage-Karte) ─────────────
create or replace function public.list_public_partners()
returns table (id uuid, name text, type text, address text, lat double precision, lng double precision, offer text)
language sql stable security definer set search_path = public as $$
  select id, name, type, address, lat, lng, offer from public.partners where active order by name;
$$;

-- Rechte
revoke execute on all functions in schema public from public, anon, authenticated;
grant execute on function public.redeem_pass(uuid, uuid)          to authenticated;
grant execute on function public.submit_story(text)               to authenticated;
grant execute on function public.review_redemption(uuid, text)    to authenticated;
grant execute on function public.partner_scans(uuid, int)         to authenticated;
grant execute on function public.list_public_partners()           to anon, authenticated;

-- ───────────── Row Level Security ─────────────
alter table public.profiles       enable row level security;
alter table public.partners       enable row level security;
alter table public.creator_passes enable row level security;
alter table public.redemptions    enable row level security;
alter table public.app_settings   enable row level security;

-- Policies rufen is_admin() auf → Ausführungsrecht für RLS-Auswertung
grant execute on function public.is_admin() to authenticated;

create policy profiles_select_own on public.profiles for select to authenticated using (id = auth.uid() or public.is_admin());
create policy profiles_update_own on public.profiles for update to authenticated using (id = auth.uid()) with check (id = auth.uid());
create policy profiles_admin_all  on public.profiles for all    to authenticated using (public.is_admin()) with check (public.is_admin());

create policy partners_select_own on public.partners for select to authenticated using (owner_id = auth.uid() or public.is_admin());
create policy partners_update_own on public.partners for update to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy partners_insert_own on public.partners for insert to authenticated
  with check (owner_id = auth.uid() and active = false and exists (select 1 from public.profiles where id = auth.uid() and role = 'partner'));
create policy partners_admin_all  on public.partners for all    to authenticated using (public.is_admin()) with check (public.is_admin());

-- Pässe: Influencer nur den eigenen, Partner nie direkt (nur via redeem_pass)
create policy passes_select_own on public.creator_passes for select to authenticated using (influencer_id = auth.uid() or public.is_admin());
create policy passes_admin_all  on public.creator_passes for all    to authenticated using (public.is_admin()) with check (public.is_admin());

create policy redemptions_select on public.redemptions for select to authenticated using (
  influencer_id = auth.uid()
  or public.is_admin()
  or exists (select 1 from public.partners p where p.id = partner_id and p.owner_id = auth.uid())
);
create policy redemptions_admin_all on public.redemptions for all to authenticated using (public.is_admin()) with check (public.is_admin());

create policy settings_read  on public.app_settings for select to authenticated using (true);
create policy settings_admin on public.app_settings for all    to authenticated using (public.is_admin()) with check (public.is_admin());

-- Ersten Admin setzen (nach der Registrierung, E-Mail anpassen):
-- update public.profiles set role = 'admin' where id = (select id from auth.users where email = 'DEINE@EMAIL');
