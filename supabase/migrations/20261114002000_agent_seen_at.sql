-- Evaluated progress is published only when it changes, so the dashboard can no longer treat
-- "the evaluation is a few seconds old" as "the agent is gone". Instead the agent's one read
-- per tick (station_snapshot) stamps agent_seen_at on the station's runtime row, at no extra
-- request, and the dashboard reads it with the rest of the station (read_station_session).

alter table public.station_runtime add column if not exists agent_seen_at timestamptz;

create or replace function public.station_snapshot(p_station_id text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  active public.sessions[];
  s public.sessions;
  rows jsonb;
  marks jsonb;
begin
  update public.station_runtime set agent_seen_at = clock_timestamp()
    where station_id = p_station_id;
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
