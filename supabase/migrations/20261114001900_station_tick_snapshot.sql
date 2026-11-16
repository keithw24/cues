-- One request instead of many for the two things that poll the database.
--
-- station_tick: the camera's heartbeat. In one call it claims the one-camera lease, reads the
--   station's session, reports what the camera is doing (what report_station_session used to
--   be called separately for) and returns the session plus the teacher's "Mark as reviewed"
--   marks. Vision used to make four requests a second for this.
-- station_snapshot: what the agent needs each tick (the active session, this session's
--   seat_state rows and the marks) in one read instead of five.
--
-- Both are backend-only (service_role). They add no tables and no columns.

create or replace function public.station_tick(
  p_station_id text, p_writer_id uuid, p_ttl_seconds integer, p_supported_activity_ids text[]
) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  claim jsonb;
  active public.sessions[];
  s public.sessions;
  ready boolean;
  report_status text;
  report_error text;
  marks jsonb := '[]'::jsonb;
begin
  claim := public.claim_station_writer(p_station_id, p_writer_id, p_ttl_seconds);
  if not coalesce((claim ->> 'granted')::boolean, false) then
    return jsonb_build_object('granted', false, 'held_seconds_ago', claim -> 'held_seconds_ago',
                              'session', null, 'marks', marks);
  end if;

  select array_agg(x) into active from public.sessions x
    where x.station_id = p_station_id and x.ended_at is null;
  if coalesce(array_length(active, 1), 0) > 1 then
    raise exception 'ambiguous active station session' using errcode = '40001';
  end if;
  if coalesce(array_length(active, 1), 0) = 1 then
    s := active[1];
  else
    select * into s from public.sessions
      where station_id = p_station_id order by started_at desc limit 1;
  end if;

  ready := s.id is not null and s.ended_at is null and s.current_activity_id is not null;
  if ready and s.current_activity_id = any (coalesce(p_supported_activity_ids, '{}')) then
    report_status := 'ready';
  elsif ready then
    report_status := 'error';
    report_error := 'unsupported_activity';
  else
    report_status := 'idle';
  end if;
  perform public.report_station_session(
    p_station_id, s.id, s.revision,
    case when report_status <> 'idle' then s.current_activity_id end,
    report_status, report_error, p_supported_activity_ids);

  if s.id is not null and s.ended_at is null then
    select coalesce(jsonb_agg(jsonb_build_object('seat_id', m.seat_id, 'marked_at', m.marked_at)),
                    '[]'::jsonb) into marks
      from public.seat_review_marks m where m.session_id = s.id;
  end if;
  return jsonb_build_object(
    'granted', true,
    'held_seconds_ago', claim -> 'held_seconds_ago',
    'session', case when s.id is null then null else jsonb_build_object(
      'id', s.id, 'station_id', s.station_id, 'current_activity_id', s.current_activity_id,
      'started_at', s.started_at, 'ended_at', s.ended_at, 'revision', s.revision) end,
    'marks', marks);
end $$;

create or replace function public.station_snapshot(p_station_id text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  active public.sessions[];
  s public.sessions;
  rows jsonb;
  marks jsonb;
begin
  select array_agg(x) into active from public.sessions x
    where x.station_id = p_station_id and x.ended_at is null;
  if coalesce(array_length(active, 1), 0) <> 1 then
    return jsonb_build_object('session', null, 'rows', '[]'::jsonb, 'marks', '[]'::jsonb);
  end if;
  s := active[1];
  select coalesce(jsonb_agg(jsonb_build_object(
      'seat_id', ss.seat_id, 'session_id', ss.session_id, 'activity_id', ss.activity_id,
      'status', ss.status, 'updated_at', ss.updated_at, 'tracking_valid', ss.tracking_valid,
      'task_score', ss.task_score, 'expression_context', ss.expression_context,
      'session_revision', ss.session_revision)), '[]'::jsonb) into rows
    from public.seat_state ss join public.seats st on st.id = ss.seat_id
    where st.station_id = p_station_id and ss.session_id = s.id
      and ss.session_revision = s.revision
      and ss.activity_id is not distinct from s.current_activity_id;
  select coalesce(jsonb_agg(jsonb_build_object('seat_id', m.seat_id, 'marked_at', m.marked_at)),
                  '[]'::jsonb) into marks
    from public.seat_review_marks m where m.session_id = s.id;
  return jsonb_build_object(
    'session', jsonb_build_object('id', s.id, 'current_activity_id', s.current_activity_id,
                                  'revision', s.revision),
    'rows', rows, 'marks', marks);
end $$;

revoke all on function public.station_tick(text, uuid, integer, text[]) from public, anon, authenticated;
revoke all on function public.station_snapshot(text) from public, anon, authenticated;
grant execute on function public.station_tick(text, uuid, integer, text[]) to service_role;
grant execute on function public.station_snapshot(text) to service_role;
