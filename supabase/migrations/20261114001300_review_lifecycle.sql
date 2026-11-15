-- Review lifecycle: (1) reviews still pending when a session ends are closed automatically,
-- (2) at most one open (pending) review per person, activity and session.
--
-- Closed-by-the-system reviews get their own status, 'expired'. They are not 'dismissed':
-- the dashboard shows 'dismissed' as the teacher's own "No support needed" decision, and
-- nobody made that decision here. Teachers still resolve reviews only as confirmed or
-- dismissed (resolve_teacher_review is unchanged); only the triggers below set 'expired'.
-- Requires 300 (teacher_reviews), 310 (sessions.ended_at) and 600 (review ownership).
begin;

-- 1. Allow the new status. The status checks were unnamed, so find them by definition.
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
  check (status in ('pending', 'confirmed', 'dismissed', 'expired'));
alter table public.teacher_reviews add constraint teacher_reviews_resolution_check
  check ((status = 'pending' and resolved_at is null)
    or (status in ('confirmed', 'dismissed', 'expired') and resolved_at is not null
      and resolved_at >= created_at));

-- The transition guard: a pending review may become confirmed, dismissed or expired,
-- once, changing nothing but status and resolved_at.
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
    if new.status not in ('confirmed', 'dismissed', 'expired') or new.resolved_at is null then
      raise exception 'review must transition to confirmed, dismissed or expired';
    end if;
  end if;
  return new;
end;
$$;

-- 2. Close the backlog once: reviews still pending in sessions that already ended.
update public.teacher_reviews r
set status = 'expired', resolved_at = greatest(pg_catalog.clock_timestamp(), r.created_at)
where r.status = 'pending'
  and exists (select 1 from public.sessions s where s.id = r.session_id and s.ended_at is not null);

-- ...and collapse duplicates in still-running sessions: keep the oldest open review per
-- person and activity, close the newer ones, so the unique index below can be built.
update public.teacher_reviews r
set status = 'expired', resolved_at = greatest(pg_catalog.clock_timestamp(), r.created_at)
where r.status = 'pending'
  and exists (
    select 1 from public.teacher_reviews older
    where older.status = 'pending'
      and older.session_id = r.session_id and older.seat_id = r.seat_id
      and older.activity_id = r.activity_id
      and (older.created_at, older.id) < (r.created_at, r.id)
  );

-- 3. One open review per person, activity and session. Once it is resolved (or expires)
-- a later evaluation may open a new one.
create unique index teacher_reviews_one_open_per_seat_activity
  on public.teacher_reviews (session_id, seat_id, activity_id) where status = 'pending';

-- 4. Closing a session closes its open reviews.
create function public.expire_reviews_when_session_ends() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  update public.teacher_reviews r
    set status = 'expired', resolved_at = greatest(pg_catalog.clock_timestamp(), r.created_at)
    where r.session_id = new.id and r.status = 'pending';
  return null;
end $$;
revoke all on function public.expire_reviews_when_session_ends() from public, anon, authenticated;
create trigger sessions_expire_reviews after update of ended_at on public.sessions
  for each row when (old.ended_at is null and new.ended_at is not null)
  execute function public.expire_reviews_when_session_ends();

-- 5. A review that arrives after its session ended (a slow evaluation) is closed at once.
create function public.expire_review_of_ended_session() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  update public.teacher_reviews r
    set status = 'expired', resolved_at = greatest(pg_catalog.clock_timestamp(), r.created_at)
    where r.id = new.id and r.status = 'pending'
      and exists (select 1 from public.sessions s
                  where s.id = new.session_id and s.ended_at is not null);
  return null;
end $$;
revoke all on function public.expire_review_of_ended_session() from public, anon, authenticated;
create trigger teacher_review_expire_if_session_ended after insert on public.teacher_reviews
  for each row execute function public.expire_review_of_ended_session();

commit;
