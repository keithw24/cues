-- Long-term classroom insights (what happened, and why Cues asked).
--
-- Three pieces, all class-level: no seat or child identifier is ever stored here, and no
-- expression data. A seat is only a position in the frame, so nothing below follows a child
-- across sessions.
--
--   session_activity_spans  how long each activity ran in a session (a trigger on sessions, so
--                           every RPC that changes the activity is covered, none is edited).
--   session_summaries       one row per ended session and activity, written once when the
--                           session ends. This is the long-term memory: it outlives the raw
--                           events, which are pruned after 90 days.
--   teacher_insights()      one request for the whole page: a teacher's own summaries, rolled up.
--
-- Requires 100 (events), 300 (teacher_reviews), 600 (sessions.teacher_id), 1800 (interventions).
begin;

-- ---- How long each activity ran ------------------------------------------------------------

create table public.session_activity_spans (
  id bigint generated always as identity primary key,
  session_id uuid not null references public.sessions (id) on delete cascade,
  activity_id text not null,
  started_at timestamptz not null,
  ended_at timestamptz,
  check (ended_at is null or ended_at >= started_at)
);
create unique index one_open_span_per_session
  on public.session_activity_spans (session_id) where ended_at is null;
create index session_activity_spans_session_idx on public.session_activity_spans (session_id);
alter table public.session_activity_spans enable row level security;
revoke all on public.session_activity_spans from anon, authenticated;
grant all on public.session_activity_spans to service_role;

-- Existing sessions: one span with the activity they have now (earlier changes were not kept).
insert into public.session_activity_spans (session_id, activity_id, started_at, ended_at)
select id, current_activity_id, started_at, ended_at
from public.sessions
where current_activity_id is not null and started_at is not null;

create function public.track_session_activity() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  stamp timestamptz := coalesce(new.ended_at, pg_catalog.clock_timestamp());
begin
  if tg_op = 'UPDATE'
     and new.current_activity_id is not distinct from old.current_activity_id
     and new.ended_at is not distinct from old.ended_at then
    return null;
  end if;
  update public.session_activity_spans
    set ended_at = greatest(stamp, started_at)
    where session_id = new.id and ended_at is null;
  if new.ended_at is null and new.current_activity_id is not null then
    insert into public.session_activity_spans (session_id, activity_id, started_at)
    values (new.id, new.current_activity_id, stamp);
  end if;
  return null;
end $$;
revoke all on function public.track_session_activity() from public, anon, authenticated;
-- Triggers on one table fire in name order: this one must close the last span before the
-- summary trigger (sessions_b_summarize, below) adds the spans up.
create trigger sessions_a_track_activity
  after insert or update of current_activity_id, ended_at on public.sessions
  for each row execute function public.track_session_activity();

-- ---- One row per ended session and activity ------------------------------------------------

create table public.session_summaries (
  session_id uuid not null references public.sessions (id) on delete cascade,
  activity_id text not null,
  teacher_id uuid not null references auth.users (id) on delete cascade,
  started_at timestamptz not null,
  class_seconds integer not null default 0 check (class_seconds >= 0),
  reviews_raised integer not null default 0 check (reviews_raised >= 0),
  confirmed integer not null default 0 check (confirmed >= 0),
  dismissed integer not null default 0 check (dismissed >= 0),
  reviewed integer not null default 0 check (reviewed >= 0),
  expired integer not null default 0 check (expired >= 0),
  pending integer not null default 0 check (pending >= 0),
  -- {"show_example": {"approved": 2, "resumed": 1}}: supports the teacher approved, and how many
  -- were followed by a successful attempt within 5 minutes.
  supports jsonb not null default '{}'::jsonb check (jsonb_typeof(supports) = 'object'),
  -- {"current_progress": 3, ...}: which evidence the agent used when it asked.
  evidence jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence) = 'object'),
  -- Seconds from request to the teacher's answer, one per answered review; the page takes the
  -- median across sessions. No seat, no name.
  decision_seconds integer[] not null default '{}',
  -- When each review was raised, for the weekday-and-hour view in the teacher's own time zone.
  raised_at timestamptz[] not null default '{}',
  summarized_at timestamptz not null default now(),
  primary key (session_id, activity_id),
  check (confirmed + dismissed + reviewed + expired + pending = reviews_raised)
);
create index session_summaries_teacher_started_idx
  on public.session_summaries (teacher_id, started_at desc);
alter table public.session_summaries enable row level security;
-- Read only through teacher_insights(); no direct browser access, no browser writes.
revoke all on public.session_summaries from anon, authenticated;
grant all on public.session_summaries to service_role;

-- Rebuild one ended session's summary from what is stored now. Safe to repeat: it replaces the
-- session's rows. A session whose raw events are already pruned keeps the summary it has.
create function public.summarize_session(p_session_id uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare s public.sessions;
begin
  select * into s from public.sessions where id = p_session_id;
  if s.id is null or s.ended_at is null or s.teacher_id is null then return; end if;
  if s.ended_at < now() - interval '90 days'
     and exists (select 1 from public.session_summaries where session_id = s.id) then
    return;
  end if;
  delete from public.session_summaries where session_id = s.id;
  insert into public.session_summaries (
    session_id, activity_id, teacher_id, started_at, class_seconds, reviews_raised,
    confirmed, dismissed, reviewed, expired, pending,
    supports, evidence, decision_seconds, raised_at
  )
  with spans as (
    select activity_id,
           coalesce(sum(extract(epoch from (ended_at - started_at))), 0)::integer as secs
    from public.session_activity_spans
    where session_id = s.id and ended_at is not null
    group by activity_id
  ),
  rev as (
    select r.id, r.activity_id, r.status, r.created_at, r.resolved_at, r.evidence_used,
           r.seat_id, i.action, i.approved_at
    from public.teacher_reviews r
    left join public.interventions i on i.review_id = r.id
    where r.session_id = s.id
  ),
  sup as (
    select activity_id, action,
           count(*) as approved,
           count(*) filter (where exists (
             select 1 from public.events e
             where e.session_id = s.id and e.seat_id = rev.seat_id
               and e.type = 'attempt_success'
               and e.created_at > rev.approved_at
               and e.created_at <= rev.approved_at + interval '5 minutes'
           )) as resumed
    from rev
    where action is not null and approved_at is not null
    group by activity_id, action
  ),
  evid as (
    select rev.activity_id, source, count(*) as uses
    from rev, jsonb_array_elements_text(rev.evidence_used) as source
    group by rev.activity_id, source
  ),
  acts as (
    select activity_id from spans union select activity_id from rev
  )
  select s.id, a.activity_id, s.teacher_id, s.started_at,
    coalesce((select secs from spans where spans.activity_id = a.activity_id), 0),
    (select count(*) from rev where rev.activity_id = a.activity_id),
    (select count(*) from rev where rev.activity_id = a.activity_id and status = 'confirmed'),
    (select count(*) from rev where rev.activity_id = a.activity_id and status = 'dismissed'),
    (select count(*) from rev where rev.activity_id = a.activity_id and status = 'reviewed'),
    (select count(*) from rev where rev.activity_id = a.activity_id and status = 'expired'),
    (select count(*) from rev where rev.activity_id = a.activity_id and status = 'pending'),
    coalesce((select jsonb_object_agg(sup.action, jsonb_build_object(
        'approved', sup.approved, 'resumed', sup.resumed))
      from sup where sup.activity_id = a.activity_id), '{}'::jsonb),
    coalesce((select jsonb_object_agg(evid.source, evid.uses)
      from evid where evid.activity_id = a.activity_id), '{}'::jsonb),
    coalesce((select array_agg(round(extract(epoch from (rev.resolved_at - rev.created_at)))::integer
        order by rev.created_at)
      from rev where rev.activity_id = a.activity_id
        and rev.status in ('confirmed', 'dismissed', 'reviewed')
        and rev.resolved_at is not null), '{}'),
    coalesce((select array_agg(rev.created_at order by rev.created_at)
      from rev where rev.activity_id = a.activity_id), '{}')
  from acts a;
end $$;
revoke all on function public.summarize_session(uuid) from public, anon, authenticated;
grant execute on function public.summarize_session(uuid) to service_role;

-- Raw events are kept for 90 days: the summaries above are the long-term record. Events of a
-- session that is still running are never removed.
create function public.prune_old_events() returns void
language sql security definer set search_path = '' as $$
  delete from public.events e
  where e.created_at < now() - interval '90 days'
    and not exists (
      select 1 from public.sessions s where s.id = e.session_id and s.ended_at is null
    );
$$;
revoke all on function public.prune_old_events() from public, anon, authenticated;
grant execute on function public.prune_old_events() to service_role;

-- When a session ends: summarize it, then drop events past 90 days (rare, so no scheduler).
create function public.summarize_ended_session() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  perform public.summarize_session(new.id);
  perform public.prune_old_events();
  return null;
end $$;
revoke all on function public.summarize_ended_session() from public, anon, authenticated;
create trigger sessions_b_summarize
  after update of ended_at on public.sessions
  for each row when (old.ended_at is null and new.ended_at is not null)
  execute function public.summarize_ended_session();

-- A review answered, or a support approved, after its session ended updates that summary.
-- A running session returns at once (summarize_session ignores sessions with no end).
create function public.resummarize_for_review() returns trigger
language plpgsql security definer set search_path = '' as $$
declare sid uuid;
begin
  if tg_table_name = 'teacher_reviews' then
    sid := new.session_id;
  else
    select session_id into sid from public.teacher_reviews where id = new.review_id;
  end if;
  if sid is not null then perform public.summarize_session(sid); end if;
  return null;
end $$;
revoke all on function public.resummarize_for_review() from public, anon, authenticated;
create trigger teacher_reviews_resummarize
  after update of status on public.teacher_reviews
  for each row when (old.status is distinct from new.status)
  execute function public.resummarize_for_review();
create trigger interventions_resummarize
  after insert on public.interventions
  for each row when (new.review_id is not null)
  execute function public.resummarize_for_review();

-- Existing ended sessions, before any pruning could remove what a summary needs.
select public.summarize_session(id) from public.sessions where ended_at is not null;

-- ---- The page: one request ----------------------------------------------------------------

create function public.teacher_insights(
  p_from timestamptz,
  p_to timestamptz,
  p_activity text default null,
  p_tz text default 'UTC'
) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
  uid uuid := auth.uid();
  span interval;
  result jsonb;
begin
  if uid is null or auth.role() is distinct from 'authenticated' then
    raise exception 'Authentication required' using errcode = '42501';
  end if;
  if p_from is null or p_to is null or p_to <= p_from or p_to - p_from > interval '400 days' then
    raise exception 'Invalid date range' using errcode = '22023';
  end if;
  begin
    perform now() at time zone p_tz;
  exception when others then
    raise exception 'Unknown time zone' using errcode = '22023';
  end;
  span := p_to - p_from;

  with cur as (
    select * from public.session_summaries
    where teacher_id = uid and started_at >= p_from and started_at < p_to
      and (p_activity is null or activity_id = p_activity)
  ),
  prev as (
    select * from public.session_summaries
    where teacher_id = uid and started_at >= p_from - span and started_at < p_from
      and (p_activity is null or activity_id = p_activity)
  ),
  decided as (
    select d from cur, unnest(cur.decision_seconds) as d
  ),
  sup as (
    select e.key as action,
           sum((e.value ->> 'approved')::integer) as approved,
           sum((e.value ->> 'resumed')::integer) as resumed
    from cur, jsonb_each(cur.supports) as e
    group by e.key
  ),
  evid as (
    select e.key as source, sum(e.value::integer) as uses
    from cur, jsonb_each_text(cur.evidence) as e(key, value)
    group by e.key
  ),
  by_activity as (
    select cur.activity_id, coalesce(a.name, cur.activity_id) as name,
           sum(cur.class_seconds) as class_seconds, sum(cur.reviews_raised) as reviews_raised
    from cur left join public.activities a on a.id = cur.activity_id
    group by cur.activity_id, a.name
  ),
  weekly as (
    select (date_trunc('week', cur.started_at at time zone p_tz))::date as week_start,
           count(distinct cur.session_id) as sessions, sum(cur.reviews_raised) as reviews_raised
    from cur group by 1
  ),
  heat as (
    select extract(dow from t at time zone p_tz)::integer as dow,
           extract(hour from t at time zone p_tz)::integer as hour,
           count(*) as count
    from cur, unnest(cur.raised_at) as t
    group by 1, 2
  )
  select jsonb_build_object(
    'range', jsonb_build_object('from', p_from, 'to', p_to),
    'totals', jsonb_build_object(
      'sessions', (select count(distinct session_id) from cur),
      'class_seconds', coalesce((select sum(class_seconds) from cur), 0),
      'reviews_raised', coalesce((select sum(reviews_raised) from cur), 0),
      'confirmed', coalesce((select sum(confirmed) from cur), 0),
      'dismissed', coalesce((select sum(dismissed) from cur), 0),
      'reviewed', coalesce((select sum(reviewed) from cur), 0),
      'expired', coalesce((select sum(expired) from cur), 0),
      'pending', coalesce((select sum(pending) from cur), 0),
      'approved_supports', coalesce((select sum(approved) from sup), 0),
      'median_decision_seconds',
        (select round((percentile_cont(0.5) within group (order by d))::numeric, 1) from decided)
    ),
    'previous', jsonb_build_object(
      'sessions', (select count(distinct session_id) from prev),
      'reviews_raised', coalesce((select sum(reviews_raised) from prev), 0)
    ),
    'weekly', coalesce((select jsonb_agg(jsonb_build_object(
        'week_start', week_start, 'sessions', sessions, 'reviews_raised', reviews_raised)
        order by week_start) from weekly), '[]'::jsonb),
    'supports', coalesce((select jsonb_agg(jsonb_build_object(
        'action', action, 'approved', approved, 'resumed', resumed)
        order by approved desc, action) from sup), '[]'::jsonb),
    'evidence', coalesce((select jsonb_object_agg(source, uses) from evid), '{}'::jsonb),
    'activities', coalesce((select jsonb_agg(jsonb_build_object(
        'activity_id', activity_id, 'name', name,
        'class_seconds', class_seconds, 'reviews_raised', reviews_raised)
        order by reviews_raised desc, name) from by_activity), '[]'::jsonb),
    'heat', coalesce((select jsonb_agg(jsonb_build_object(
        'dow', dow, 'hour', hour, 'count', count) order by dow, hour) from heat), '[]'::jsonb)
  ) into result;
  return result;
end $$;
revoke all on function public.teacher_insights(timestamptz, timestamptz, text, text)
  from public, anon;
grant execute on function public.teacher_insights(timestamptz, timestamptz, text, text)
  to authenticated;

commit;
