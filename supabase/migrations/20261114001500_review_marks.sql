-- "Mark as reviewed": the teacher has checked in with a child who was flagged.
--
--  1. mark_seat_reviewed(session, seat) closes that child's open review requests and
--     records a mark. Vision reads the mark to put the child back to working and restart
--     the no-progress timer; the agent reads it to restart its stall detection.
--  2. When a child's task is completed, their open review requests are closed too.
--
-- Reviews closed by a teacher's mark get the status 'reviewed'. Reviews closed because the
-- task was completed (or the session ended) stay 'expired': nobody made a decision.
-- Requires 300/1300 (teacher_reviews), 310 (sessions, require_station_teacher).
begin;

-- 'reviewed' joins the allowed review statuses (constraints found by definition, as in 1300).
do $$
declare c record;
begin
  for c in
    select conname from pg_constraint
    where conrelid = 'public.teacher_reviews'::regclass and contype = 'c'
      and pg_get_constraintdef(oid) like '%status%'
  loop
    execute format('alter table public.teacher_reviews drop constraint %I', c.conname);
  end loop;
end $$;
alter table public.teacher_reviews add constraint teacher_reviews_status_check
  check (status in ('pending', 'confirmed', 'dismissed', 'expired', 'reviewed'));
alter table public.teacher_reviews add constraint teacher_reviews_resolution_check
  check ((status = 'pending' and resolved_at is null)
    or (status in ('confirmed', 'dismissed', 'expired', 'reviewed') and resolved_at is not null
      and resolved_at >= created_at));

create or replace function public.guard_teacher_review_transition() returns trigger
language plpgsql set search_path = '' as $$
begin
  if TG_OP = 'INSERT' then
    if new.status <> 'pending' or new.resolved_at is not null then
      raise exception 'review must be created pending';
    end if;
  else
    if old.status <> 'pending' then
      raise exception 'review already resolved';
    end if;
    if (to_jsonb(new) - 'status' - 'resolved_at') is distinct from
       (to_jsonb(old) - 'status' - 'resolved_at') then
      raise exception 'trusted review fields are immutable';
    end if;
    if new.status not in ('confirmed', 'dismissed', 'expired', 'reviewed')
       or new.resolved_at is null then
      raise exception 'review must transition to confirmed, dismissed, expired or reviewed';
    end if;
  end if;
  return new;
end;
$$;

-- The mark itself: one row per child per session; marking again moves it forward.
create table public.seat_review_marks (
  session_id uuid not null references public.sessions(id) on delete cascade,
  seat_id text not null,
  marked_at timestamptz not null default now(),
  marked_by uuid references auth.users(id) on delete set null,
  primary key (session_id, seat_id)
);
alter table public.seat_review_marks enable row level security;
revoke all on public.seat_review_marks from anon, authenticated;
grant all on public.seat_review_marks to service_role;  -- vision and the agent read it

create function public.mark_seat_reviewed(p_session_id uuid, p_seat_id text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := auth.uid();
  s public.sessions;
  closed integer;
  stamp timestamptz;
begin
  if uid is null or auth.role() is distinct from 'authenticated' then
    raise exception 'Authentication required' using errcode = '42501';
  end if;
  select * into s from public.sessions where id = p_session_id for share;
  if s.id is null or s.ended_at is not null or s.station_id is null then
    raise exception 'Session unavailable' using errcode = '22023';
  end if;
  -- Only a teacher of this station; the browser never says whose child or station it is.
  perform public.require_station_teacher(s.station_id);
  if not exists (select 1 from public.seats
                 where id = p_seat_id and station_id = s.station_id) then
    raise exception 'Unknown person for this station' using errcode = '22023';
  end if;
  insert into public.seat_review_marks(session_id, seat_id, marked_at, marked_by)
    values (p_session_id, p_seat_id, pg_catalog.clock_timestamp(), uid)
    on conflict (session_id, seat_id)
    do update set marked_at = excluded.marked_at, marked_by = excluded.marked_by
    returning marked_at into stamp;
  update public.teacher_reviews r
    set status = 'reviewed', resolved_at = greatest(pg_catalog.clock_timestamp(), r.created_at)
    where r.session_id = p_session_id and r.seat_id = p_seat_id and r.status = 'pending';
  get diagnostics closed = row_count;
  return jsonb_build_object('closed', closed, 'marked_at', stamp);
end $$;
revoke all on function public.mark_seat_reviewed(uuid, text) from public, anon, service_role;
grant execute on function public.mark_seat_reviewed(uuid, text) to authenticated;

-- Completing the task closes that child's open reviews for it.
create function public.expire_reviews_when_task_done() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  update public.teacher_reviews r
    set status = 'expired', resolved_at = greatest(pg_catalog.clock_timestamp(), r.created_at)
    where r.session_id = new.session_id and r.seat_id = new.seat_id
      and r.activity_id = new.activity_id and r.status = 'pending';
  return null;
end $$;
revoke all on function public.expire_reviews_when_task_done() from public, anon, authenticated;
create trigger seat_state_done_expires_reviews
  after insert or update of status on public.seat_state
  for each row when (new.status = 'done')
  execute function public.expire_reviews_when_task_done();

-- One-time: close open reviews for children who have already completed their task.
update public.teacher_reviews r
  set status = 'expired', resolved_at = greatest(pg_catalog.clock_timestamp(), r.created_at)
  where r.status = 'pending' and exists (
    select 1 from public.seat_state ss
    where ss.session_id = r.session_id and ss.seat_id = r.seat_id
      and ss.activity_id = r.activity_id and ss.status = 'done');

commit;
