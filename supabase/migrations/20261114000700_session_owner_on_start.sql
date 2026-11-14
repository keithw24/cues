-- Sessions created by a teacher are owned by that teacher (requires migration 006).
-- The owner is always the authenticated caller; the browser never supplies a teacher ID.
-- Only the insert branch changes: existing (historical) sessions stay as they are.
begin;
create or replace function public.start_station_activity(
  p_station_id text, p_activity_id text,
  p_expected_session_id uuid, p_expected_revision integer
) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare s public.sessions;
begin
  perform public.require_station_teacher(p_station_id);
  perform 1 from public.stations where id = p_station_id for update;
  if not found then
    raise exception 'Station unavailable';
  end if;
  if not exists (select 1 from public.activities where id = p_activity_id) then
    raise exception 'Activity unavailable';
  end if;
  if exists (select 1 from public.station_runtime where station_id = p_station_id)
    and not exists (
      select 1 from public.station_runtime
      where station_id = p_station_id and p_activity_id = any(supported_activity_ids)
    ) then
    raise exception 'Activity unavailable on station';
  end if;
  select * into s from public.sessions
    where station_id = p_station_id and ended_at is null for update;
  if s.id is distinct from p_expected_session_id
    or (s.id is not null and s.revision is distinct from p_expected_revision) then
    raise exception 'Session changed; refresh before acting' using errcode = '40001';
  end if;
  if s.id is null then
    insert into public.sessions(station_id, current_activity_id, teacher_id)
      values(p_station_id, p_activity_id, auth.uid()) returning * into s;
  else
    update public.sessions
      set current_activity_id = p_activity_id, revision = revision + 1
      where id = s.id returning * into s;
  end if;
  update public.stations set session_managed = true where id = p_station_id;
  return to_jsonb(s);
end $$;
revoke all on function public.start_station_activity(text,text,uuid,integer) from public, anon;
grant execute on function public.start_station_activity(text,text,uuid,integer) to authenticated;
commit;
