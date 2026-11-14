-- Persistent teacher review lifecycle; no instructional-change approval.
begin;

create table public.teacher_reviews (
  id uuid primary key,
  created_at timestamptz not null,
  session_id uuid not null,
  seat_id text not null,
  activity_id text not null,
  priority text not null check (priority in ('normal', 'elevated')),
  -- Complete AgentEvaluationRequest for lossless typed reconstruction/deduplication.
  evaluation jsonb not null unique,
  decision text not null check (decision = 'teacher_review_warranted'),
  rationale text not null check (length(btrim(rationale)) between 1 and 500),
  evidence_used jsonb not null check (
    jsonb_typeof(evidence_used) = 'array'
    and jsonb_array_length(evidence_used) between 1 and 4
    and evidence_used <@ '["current_progress", "activity", "recent_progress_history", "prompt_history"]'::jsonb
  ),
  status text not null default 'pending' check (status in ('pending', 'confirmed', 'dismissed')),
  resolved_at timestamptz,
  check ((status = 'pending' and resolved_at is null)
    or (status in ('confirmed', 'dismissed') and resolved_at is not null
      and resolved_at >= created_at)),
  check ((jsonb_typeof(evaluation) = 'object'
    and evaluation->>'session_id' = session_id::text
    and evaluation->>'seat_id' = seat_id
    and evaluation->>'activity_id' = activity_id
    and evaluation#>>'{escalation,priority}' = priority
    and evaluation#>>'{escalation,should_evaluate}' = 'true'
    and evaluation#>>'{progress,trend}' = 'stalled') is true)
);

create index teacher_reviews_pending_created_idx on public.teacher_reviews (created_at, id)
  where status = 'pending';
create index teacher_reviews_session_seat_idx on public.teacher_reviews (session_id, seat_id);

-- Guard even server-side updates: only one pending -> resolved transition is allowed.
create function public.guard_teacher_review_transition() returns trigger
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
    if new.status not in ('confirmed', 'dismissed') or new.resolved_at is null then
      raise exception 'review must transition to confirmed or dismissed';
    end if;
  end if;
  return new;
end;
$$;
revoke all on function public.guard_teacher_review_transition() from public;
create trigger teacher_review_transition before insert or update on public.teacher_reviews
  for each row execute function public.guard_teacher_review_transition();

alter table public.teacher_reviews enable row level security;
revoke all on public.teacher_reviews from anon, authenticated;
grant select on public.teacher_reviews to anon, authenticated;
grant select, insert, update on public.teacher_reviews to service_role;

-- Existing project pattern: only simulated demo-seat rows are browser-readable.
-- No browser writes/RPC. Future authenticated teacher actions must use the backend.
create policy demo_teacher_reviews_read on public.teacher_reviews
  for select to anon, authenticated using (
    exists (select 1 from public.seats s
      where s.id = teacher_reviews.seat_id and s.is_simulated is true)
  );

alter publication supabase_realtime add table public.teacher_reviews;
commit;
