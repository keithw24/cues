-- Single-use operator-issued station invitations. No session ownership changes.
begin;
create table public.station_pairing_codes (
  id uuid primary key default gen_random_uuid(),
  station_id text not null references public.stations(id),
  code_hash text not null unique check (code_hash ~ '^[0-9a-f]{64}$'),
  expires_at timestamptz not null,
  used_at timestamptz,
  used_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  check (expires_at > created_at),
  check ((used_at is null) = (used_by is null))
);
alter table public.station_pairing_codes enable row level security;
revoke all on public.station_pairing_codes from public, anon, authenticated;
grant all on public.station_pairing_codes to service_role;

-- UUID randomness gives a high-entropy code; formatting/case are insignificant.
-- Uses built-in PostgreSQL SHA-256, without an extension dependency.
create function public.station_pairing_code_hash(code text) returns text
language sql immutable strict set search_path = '' as $$
  select pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
    pg_catalog.upper(pg_catalog.regexp_replace(code, '[-[:space:]]', '', 'g')),
    'UTF8')), 'hex');
$$;
revoke all on function public.station_pairing_code_hash(text) from public, anon, authenticated;

create function public.issue_station_pairing_code(
  p_station_id text, p_ttl_seconds integer default 600
) returns table(code text, expires_at timestamptz)
language plpgsql security definer set search_path = '' as $$
declare plaintext text; expiry timestamptz;
begin
  if p_ttl_seconds is null or p_ttl_seconds < 1 or p_ttl_seconds > 3600 then
    raise exception 'Pairing lifetime must be between 1 and 3600 seconds';
  end if;
  plaintext := pg_catalog.upper(pg_catalog.gen_random_uuid()::text);
  expiry := pg_catalog.clock_timestamp() + pg_catalog.make_interval(secs => p_ttl_seconds);
  insert into public.station_pairing_codes(station_id, code_hash, expires_at)
    values(p_station_id, public.station_pairing_code_hash(plaintext), expiry);
  return query select plaintext, expiry;
end;
$$;
revoke all on function public.issue_station_pairing_code(text,integer) from public, anon, authenticated;
grant execute on function public.issue_station_pairing_code(text,integer) to service_role;

create function public.redeem_station_pairing_code(code text)
returns table(station_id text)
language plpgsql security definer set search_path = '' as $$
declare invitation public.station_pairing_codes; teacher uuid := auth.uid();
begin
  if teacher is null or auth.role() is distinct from 'authenticated' then
    raise exception 'Authentication required' using errcode = '42501';
  end if;
  if code is null or pg_catalog.length(code) > 128 then
    raise exception 'Invalid or unavailable pairing code' using errcode = '22023';
  end if;
  select c.* into invitation from public.station_pairing_codes c
    where c.code_hash = public.station_pairing_code_hash(code) for update;
  if not found or invitation.used_at is not null
    or invitation.expires_at <= pg_catalog.clock_timestamp() then
    raise exception 'Invalid or unavailable pairing code' using errcode = '22023';
  end if;
  insert into public.station_teachers(station_id, teacher_id)
    values(invitation.station_id, teacher) on conflict do nothing;
  update public.station_pairing_codes c
    set used_at = pg_catalog.clock_timestamp(), used_by = teacher
    where c.id = invitation.id;
  return query select invitation.station_id;
end;
$$;
revoke all on function public.redeem_station_pairing_code(text) from public, anon, service_role;
grant execute on function public.redeem_station_pairing_code(text) to authenticated;
commit;
