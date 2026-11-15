-- The dashboard's "Last hour" timeline: when children were flagged.
--
-- The browser cannot read the events table, and the pending-review queue forgets a review
-- once it is closed, so closed reviews and vision's own flags never reached the timeline.
-- read_station_flags returns, for the signed-in teacher's own sessions at their station,
-- just the seat, the kind of flag and the time:
--   'review'         a review was requested (any status, so closed ones still show)
--   'review_needed'  vision put the child in the review band
--   'no_progress'    vision flagged no progress (the "Needs Review" status)
-- No event payload, score, or expression data is returned. Requires 310 and 1300.
begin;

create function public.read_station_flags(p_station_id text, p_since timestamptz default null)
returns table (seat_id text, kind text, at timestamptz)
language plpgsql security definer set search_path = '' as $$
declare
  since timestamptz := greatest(
    coalesce(p_since, pg_catalog.now() - interval '1 hour'),
    pg_catalog.now() - interval '24 hours');
begin
  perform public.require_station_teacher(p_station_id);
  return query
  select f.seat_id, f.kind, f.at
  from (
    select e.seat_id as seat_id, e.type as kind, e.created_at as at
    from public.events e
    join public.sessions s on s.id = e.session_id
    where s.station_id = p_station_id and s.teacher_id = auth.uid()
      and e.type in ('no_progress', 'review_needed') and e.created_at >= since
    union all
    select r.seat_id, 'review'::text, r.created_at
    from public.teacher_reviews r
    join public.sessions s on s.id = r.session_id
    where s.station_id = p_station_id and s.teacher_id = auth.uid() and r.created_at >= since
  ) f
  order by f.at desc
  limit 300;
end $$;
revoke all on function public.read_station_flags(text, timestamptz) from public, anon, service_role;
grant execute on function public.read_station_flags(text, timestamptz) to authenticated;

commit;
