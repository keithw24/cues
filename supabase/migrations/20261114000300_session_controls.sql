-- Teacher-authorized lifecycle. No activity model changes or browser table writes.
begin;
create table public.station_teachers (
  station_id text not null references public.stations(id),
  teacher_id uuid not null references auth.users(id) on delete cascade,
  primary key (station_id, teacher_id)
);
alter table public.station_teachers enable row level security;
revoke all on public.station_teachers from anon, authenticated;
grant all on public.station_teachers to service_role;
alter table public.sessions add column station_id text references public.stations(id),
  add column ended_at timestamptz,
  add column revision integer not null default 0;
-- Preserve known legacy session IDs. Ambiguous legacy associations require an
-- explicit administrator decision rather than guessing which session to end.
update public.sessions s set station_id = x.station_id
from (select ss.session_id, min(se.station_id) station_id
      from public.seat_state ss join public.seats se on se.id = ss.seat_id
      group by ss.session_id having count(distinct se.station_id) = 1) x
where s.id = x.session_id;
create unique index one_active_session_per_station on public.sessions(station_id)
  where ended_at is null and station_id is not null;

create function public.require_station_teacher(p_station_id text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if auth.uid() is null or not exists (
    select 1 from public.station_teachers where station_id = p_station_id and teacher_id = auth.uid()
  ) then raise exception 'Not authorized for station' using errcode = '42501'; end if;
end $$;
revoke all on function public.require_station_teacher(text) from public, anon, authenticated;

create function public.read_station_session(p_station_id text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare result jsonb;
begin
  perform public.require_station_teacher(p_station_id);
  select jsonb_build_object('session', (
    select to_jsonb(s) from public.sessions s where s.station_id = p_station_id and s.ended_at is null
  ), 'activities', coalesce((select jsonb_agg(jsonb_build_object('id', a.id, 'name', a.name) order by a.name)
     from public.activities a), '[]'::jsonb)) into result;
  return result;
end $$;

create function public.start_station_activity(p_station_id text, p_activity_id text,
  p_expected_session_id uuid, p_expected_revision integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare current_session public.sessions;
begin
  perform public.require_station_teacher(p_station_id);
  -- Serialize even when there is no active session row yet.
  perform 1 from public.stations where id = p_station_id for update;
  if not found then raise exception 'Station unavailable'; end if;
  if not exists (select 1 from public.activities where id = p_activity_id) then
    raise exception 'Activity unavailable'; end if;
  select * into current_session from public.sessions
    where station_id = p_station_id and ended_at is null for update;
  if current_session.id is distinct from p_expected_session_id or
    (current_session.id is not null and current_session.revision is distinct from p_expected_revision) then
    raise exception 'Session changed; refresh before acting' using errcode = '40001';
  end if;
  if current_session.id is null then
    insert into public.sessions(station_id, current_activity_id)
      values(p_station_id, p_activity_id) returning * into current_session;
  else
    update public.sessions set current_activity_id = p_activity_id, revision = revision + 1
      where id = current_session.id returning * into current_session;
  end if;
  return to_jsonb(current_session);
end $$;

create function public.end_station_session(p_station_id text, p_expected_session_id uuid,
  p_expected_revision integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare current_session public.sessions;
begin
  perform public.require_station_teacher(p_station_id);
  perform 1 from public.stations where id = p_station_id for update;
  if not found then raise exception 'Station unavailable'; end if;
  update public.sessions set ended_at = now(), revision = revision + 1
    where station_id = p_station_id and id = p_expected_session_id
      and revision = p_expected_revision and ended_at is null
    returning * into current_session;
  if current_session.id is null then raise exception 'Session changed; refresh before acting' using errcode = '40001'; end if;
  return to_jsonb(current_session);
end $$;
revoke all on function public.read_station_session(text),
  public.start_station_activity(text,text,uuid,integer),
  public.end_station_session(text,uuid,integer) from public, anon;
grant execute on function public.read_station_session(text),
  public.start_station_activity(text,text,uuid,integer),
  public.end_station_session(text,uuid,integer) to authenticated;
-- Session changes supplement the existing seat_state stream.
alter publication supabase_realtime add table public.sessions;
create policy teacher_sessions_read on public.sessions for select to authenticated
  using (exists (select 1 from public.station_teachers st where st.station_id = sessions.station_id and st.teacher_id = auth.uid()));
-- Membership self-read is needed for the session RLS policy, never membership writes.
grant select on public.station_teachers to authenticated;
create policy own_station_membership on public.station_teachers for select to authenticated using (teacher_id = auth.uid());
commit;
