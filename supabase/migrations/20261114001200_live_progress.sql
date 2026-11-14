begin;
-- Agent-owned summary; vision upserts omit this column. No camera data.
alter table public.seat_state add column evaluated_progress jsonb;
create function public.publish_task_progress(p_seat_id text, p_session_id uuid,
 p_activity_id text, p_revision integer, p_observed_at timestamptz, p_progress jsonb)
returns boolean language plpgsql security definer set search_path='' as $$
declare changed integer;
begin
 perform 1 from public.sessions s join public.seats se on se.station_id=s.station_id
   where s.id=p_session_id and s.ended_at is null and se.id=p_seat_id
   and s.current_activity_id=p_activity_id and s.revision=p_revision for share of s;
 if not found then return false; end if;
 if p_progress->>'trend' not in ('improving','stalled','completed','unknown')
   or p_progress->>'trend' is null
   or jsonb_typeof(p_progress->'stalled_seconds') is distinct from 'number'
   or (p_progress->>'stalled_seconds')::numeric < 0
   or jsonb_typeof(p_progress->'recent') is distinct from 'array'
   or jsonb_array_length(p_progress->'recent') > 10 then
   raise exception 'Invalid progress summary' using errcode='22023';
 end if;
 update public.seat_state ss set evaluated_progress=p_progress || jsonb_build_object(
   'session_id',p_session_id,'activity_id',p_activity_id,'session_revision',p_revision,
   'observed_at',p_observed_at)
 where ss.seat_id=p_seat_id and ss.session_id=p_session_id
   and ss.activity_id=p_activity_id and ss.session_revision=p_revision
   and ss.updated_at=p_observed_at;
 get diagnostics changed=row_count;
 return changed=1;
end $$;
revoke all on function public.publish_task_progress(text,uuid,text,integer,timestamptz,jsonb)
 from public,anon,authenticated;
grant execute on function public.publish_task_progress(text,uuid,text,integer,timestamptz,jsonb)
 to service_role;
commit;
