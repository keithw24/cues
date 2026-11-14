begin;
create table public.teacher_notification_settings (
  user_id uuid primary key references auth.users(id) on delete cascade,
  notification_opt_in boolean not null default false,
  notification_opted_in_at timestamptz,
  notification_phone text check (notification_phone is null or notification_phone ~ '^\+[1-9][0-9]{7,14}$'),
  first_name text,
  last_name text,
  photon_project_id text,
  photon_registration_status text not null default 'unregistered'
    check (photon_registration_status in ('unregistered','registering','registered','failed')),
  photon_registered_at timestamptz,
  photon_registration_error text check (photon_registration_error in (
    'invalid_phone','imessage_not_enabled','shared_line_unavailable',
    'authentication_failed','provider_failure','network_failure','configuration_missing')),
  registration_attempt uuid,
  updated_at timestamptz not null default now(),
  check (not notification_opt_in or (notification_phone is not null and notification_opted_in_at is not null)),
  check (photon_registration_status <> 'registered' or
    (notification_opt_in and photon_registered_at is not null and photon_project_id is not null))
);
alter table public.teacher_notification_settings enable row level security;
revoke all on public.teacher_notification_settings from public, anon, authenticated;
grant select on public.teacher_notification_settings to authenticated;
grant all on public.teacher_notification_settings to service_role;
create policy own_notification_settings on public.teacher_notification_settings
  for select to authenticated using (user_id = auth.uid());

-- Same transaction as profile edits: consent/eligibility cannot follow a new phone.
create function public.invalidate_teacher_notification_phone() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  update public.teacher_notification_settings set
    notification_opt_in = false, notification_opted_in_at = null,
    notification_phone = null, photon_registration_status = 'unregistered',
    photon_registered_at = null, photon_registration_error = null,
    registration_attempt = null, updated_at = clock_timestamp()
    where user_id = old.user_id;
  return new;
end;
$$;
revoke all on function public.invalidate_teacher_notification_phone() from public, anon, authenticated;
create trigger teacher_notification_phone_changed after update of phone_number on public.teacher_profiles
for each row when (old.phone_number is distinct from new.phone_number)
execute function public.invalidate_teacher_notification_phone();

-- Only the authenticated backend endpoint may record consent. Lock profile first
-- to serialize consent capture with profile phone-change invalidation.
create function public.prepare_teacher_notification_registration(
  p_user_id uuid, p_opt_in boolean, p_first_name text, p_last_name text, p_project_id text
) returns setof public.teacher_notification_settings
language plpgsql security definer set search_path = '' as $$
declare phone text; existing public.teacher_notification_settings;
begin
  select p.phone_number into phone from public.teacher_profiles p
    where p.user_id = p_user_id for update;
  if not found then raise exception 'Profile required' using errcode='22023'; end if;
  if p_opt_in is null then raise exception 'Explicit consent required' using errcode='22023'; end if;
  if p_opt_in and (phone is null or phone !~ '^\+[1-9][0-9]{7,14}$'
    or length(btrim(coalesce(p_first_name,''))) not between 1 and 80
    or length(btrim(coalesce(p_last_name,''))) not between 1 and 80
    or nullif(btrim(p_project_id),'') is null) then
    raise exception 'Valid phone and explicit names required' using errcode='22023';
  end if;
  select * into existing from public.teacher_notification_settings where user_id=p_user_id for update;
  if p_opt_in and existing.notification_opt_in and existing.notification_phone=phone
    and existing.photon_project_id=p_project_id then
    if existing.photon_registration_status='registered' then
      return next existing; return;
    end if;
    if existing.photon_registration_status='registering'
      and existing.updated_at > clock_timestamp()-interval '30 seconds' then
      raise exception 'Registration in progress' using errcode='55P03';
    end if;
  end if;
  return query insert into public.teacher_notification_settings as target (
    user_id,notification_opt_in,notification_opted_in_at,notification_phone,
    first_name,last_name,photon_project_id,photon_registration_status,registration_attempt
  ) values (p_user_id,p_opt_in,case when p_opt_in then clock_timestamp() end,
    case when p_opt_in then phone end,btrim(p_first_name),btrim(p_last_name),p_project_id,
    case when p_opt_in then 'registering' else 'unregistered' end,gen_random_uuid())
  on conflict(user_id) do update set
    notification_opt_in=excluded.notification_opt_in,
    notification_opted_in_at=excluded.notification_opted_in_at,
    notification_phone=excluded.notification_phone,first_name=excluded.first_name,
    last_name=excluded.last_name,photon_project_id=excluded.photon_project_id,
    photon_registration_status=excluded.photon_registration_status,
    registration_attempt=excluded.registration_attempt,photon_registered_at=null,
    photon_registration_error=null,updated_at=clock_timestamp()
  returning target.*;
end;
$$;
revoke all on function public.prepare_teacher_notification_registration(uuid,boolean,text,text,text)
  from public, anon, authenticated;
grant execute on function public.prepare_teacher_notification_registration(uuid,boolean,text,text,text)
  to service_role;
commit;
