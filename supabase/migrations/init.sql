-- Black Card Protocol – Nürnberg Creator & Partner Network
-- Im Supabase SQL-Editor ausführen.

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
  active     boolean not null default true,
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
  status        text not null default 'pending' check (status in ('pending','story_submitted','flagged')),
  story_url     text,
  redeemed_at   timestamptz not null default now()
);

create index if not exists redemptions_partner_idx    on public.redemptions(partner_id, redeemed_at desc);
create index if not exists redemptions_influencer_idx on public.redemptions(influencer_id, redeemed_at desc);
create index if not exists partners_owner_idx         on public.partners(owner_id);

-- ───────────── Hilfsfunktionen ─────────────
create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles where id = auth.uid() and role = 'admin');
$$;

-- Neuer Auth-User → Profil (immer 'influencer') + Pass
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, role, name)
  values (new.id, 'influencer', coalesce(new.raw_user_meta_data->>'name', split_part(new.email, '@', 1)));
  insert into public.creator_passes (influencer_id) values (new.id);
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

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

-- ───────────── RPC: Scan / Einlösung (atomar, serverseitig validiert) ─────────────
create or replace function public.redeem_pass(p_token uuid, p_partner_id uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  v_pass public.creator_passes;
  v_prof public.profiles;
  v_cooldown interval := interval '7 days';
begin
  if not exists (select 1 from public.partners
                 where id = p_partner_id and active
                   and (owner_id = auth.uid() or public.is_admin())) then
    return jsonb_build_object('ok', false, 'reason', 'Partner nicht berechtigt oder inaktiv');
  end if;

  select * into v_pass from public.creator_passes where pass_token = p_token for update;
  if not found then
    return jsonb_build_object('ok', false, 'reason', 'Pass existiert nicht');
  end if;

  select * into v_prof from public.profiles where id = v_pass.influencer_id;
  if v_prof.is_banned then
    return jsonb_build_object('ok', false, 'reason', 'Creator ist gesperrt', 'name', v_prof.name);
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
     set status = 'locked', cooldown_until = now() + v_cooldown
   where id = v_pass.id;

  return jsonb_build_object('ok', true, 'name', v_prof.name, 'trust_score', v_prof.trust_score);
end $$;

-- ───────────── RPC: Story-Link einreichen (entsperrt den Pass) ─────────────
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

  select id into v_id from public.redemptions
   where influencer_id = auth.uid() and status = 'pending'
   order by redeemed_at desc limit 1 for update;
  if v_id is null then
    return jsonb_build_object('ok', false, 'reason', 'Keine offene Einlösung');
  end if;

  update public.redemptions set story_url = p_url, status = 'story_submitted' where id = v_id;
  update public.creator_passes set status = 'active'
   where influencer_id = auth.uid() and status = 'locked';
  update public.profiles set trust_score = least(100, trust_score + 2) where id = auth.uid();
  return jsonb_build_object('ok', true);
end $$;

grant execute on function public.redeem_pass(uuid, uuid) to authenticated;
grant execute on function public.submit_story(text)      to authenticated;
revoke execute on function public.redeem_pass(uuid, uuid) from anon, public;
revoke execute on function public.submit_story(text)      from anon, public;

-- ───────────── Row Level Security ─────────────
alter table public.profiles       enable row level security;
alter table public.partners       enable row level security;
alter table public.creator_passes enable row level security;
alter table public.redemptions    enable row level security;

-- profiles: jeder sich selbst, Admin alles
create policy profiles_select_own on public.profiles for select using (id = auth.uid() or public.is_admin());
create policy profiles_update_own on public.profiles for update using (id = auth.uid()) with check (id = auth.uid());
create policy profiles_admin_all  on public.profiles for all    using (public.is_admin()) with check (public.is_admin());

-- partners: Inhaber sieht seine, Admin verwaltet alle
create policy partners_select_own on public.partners for select using (owner_id = auth.uid() or public.is_admin());
create policy partners_admin_all  on public.partners for all    using (public.is_admin()) with check (public.is_admin());

-- creator_passes: Influencer nur den eigenen Pass (lesen), Admin alles.
-- Partner lesen Pässe NIE direkt, sondern nur über redeem_pass().
create policy passes_select_own on public.creator_passes for select using (influencer_id = auth.uid() or public.is_admin());
create policy passes_admin_all  on public.creator_passes for all    using (public.is_admin()) with check (public.is_admin());

-- redemptions: Partner nur Scans ihrer Standorte, Influencer eigene, Admin alles
create policy redemptions_select on public.redemptions for select using (
  influencer_id = auth.uid()
  or public.is_admin()
  or exists (select 1 from public.partners p where p.id = partner_id and p.owner_id = auth.uid())
);
create policy redemptions_admin_all on public.redemptions for all using (public.is_admin()) with check (public.is_admin());

-- Ersten Admin anlegen (E-Mail anpassen, nach der Registrierung ausführen):
-- update public.profiles set role = 'admin' where id = (select id from auth.users where email = 'DEINE@EMAIL');
-- Partner-Accounts: Rolle setzen + Partner mit owner_id verknüpfen (oder im Admin-Dashboard).
