-- Optional database smoke: run with psql after migrations, as a database owner.
-- Synthetic fixtures are rolled back. No Supabase credentials are needed for
-- an isolated local PostgreSQL instance with anon/authenticated/service_role roles.
\set ON_ERROR_STOP on
begin;

insert into public.seats (id, is_simulated) values
  ('REVIEW-SQL-DEMO', true), ('REVIEW-SQL-PRIVATE', false);
insert into public.teacher_reviews (
  id, created_at, session_id, seat_id, activity_id, priority,
  evaluation, decision, rationale, evidence_used
)
select id::uuid, '2020-01-01T00:00:00Z'::timestamptz,
  '00000000-0000-0000-0000-000000000001'::uuid, seat, 'raise_hand', 'elevated',
  jsonb_build_object(
    'session_id', '00000000-0000-0000-0000-000000000001', 'seat_id', seat,
    'activity_id', 'raise_hand', 'observed_at', '2020-01-01T00:00:00+00:00',
    'progress', jsonb_build_object('trend', 'stalled', 'stalled_seconds', 30),
    'escalation', jsonb_build_object('should_evaluate', true, 'priority', 'elevated',
      'reason', 'prolonged_stalled_progress')
  ), 'teacher_review_warranted', 'Repeated prolonged stalls.', '["current_progress"]'::jsonb
from (values
  ('00000000-0000-0000-0000-000000000101', 'REVIEW-SQL-DEMO'),
  ('00000000-0000-0000-0000-000000000102', 'REVIEW-SQL-PRIVATE')
) as fixtures(id, seat);

set local role anon;
do $$
declare denied boolean := false;
begin
  if (select count(*) from public.teacher_reviews
      where seat_id like 'REVIEW-SQL-%') <> 1 then
    raise exception 'RLS must expose only the simulated review';
  end if;
  begin
    update public.teacher_reviews set status = 'confirmed', resolved_at = now()
      where seat_id = 'REVIEW-SQL-DEMO';
  exception when insufficient_privilege then denied := true;
  end;
  if not denied then raise exception 'anonymous update unexpectedly allowed'; end if;
  denied := false;
  begin
    insert into public.teacher_reviews select * from public.teacher_reviews
      where seat_id = 'REVIEW-SQL-DEMO';
  exception when insufficient_privilege then denied := true;
  end;
  if not denied then raise exception 'anonymous insert unexpectedly allowed'; end if;
end;
$$;
reset role;

set local role service_role;
do $$
declare denied boolean := false;
begin
  begin
    update public.teacher_reviews set rationale = 'Rewritten rationale'
      where seat_id = 'REVIEW-SQL-DEMO';
  exception when raise_exception then denied := true;
  end;
  if not denied then raise exception 'trusted field rewrite unexpectedly allowed'; end if;
end;
$$;
update public.teacher_reviews set status = 'confirmed', resolved_at = now()
  where seat_id = 'REVIEW-SQL-DEMO' and status = 'pending';
update public.teacher_reviews set status = 'dismissed', resolved_at = now()
  where seat_id = 'REVIEW-SQL-PRIVATE' and status = 'pending';
-- Same request from another process must not overwrite/reopen a resolved row.
insert into public.teacher_reviews (
  id, created_at, session_id, seat_id, activity_id, priority,
  evaluation, decision, rationale, evidence_used
)
select '00000000-0000-0000-0000-000000000103'::uuid, created_at, session_id, seat_id,
  activity_id, priority, evaluation, decision, 'A duplicate must not rewrite this.', evidence_used
from public.teacher_reviews where seat_id = 'REVIEW-SQL-DEMO'
on conflict (evaluation) do nothing;
do $$
declare denied boolean; target text;
begin
  foreach target in array array['confirmed', 'dismissed'] loop
    denied := false;
    begin
      update public.teacher_reviews set status = target, resolved_at = now()
        where seat_id = 'REVIEW-SQL-DEMO';
    exception when raise_exception then denied := true;
    end;
    if not denied then raise exception 're-resolution unexpectedly allowed'; end if;
  end loop;
  if exists (select 1 from public.teacher_reviews
      where seat_id like 'REVIEW-SQL-%' and status = 'pending') then
    raise exception 'resolved rows still pending';
  end if;
  if (select count(*) from public.teacher_reviews where seat_id = 'REVIEW-SQL-DEMO') <> 1
      or exists (select 1 from public.teacher_reviews where seat_id = 'REVIEW-SQL-DEMO'
        and rationale <> 'Repeated prolonged stalls.') then
    raise exception 'duplicate insert changed original review';
  end if;
end;
$$;
reset role;

do $$
begin
  if not exists (select 1 from pg_publication_tables
      where pubname = 'supabase_realtime' and tablename = 'teacher_reviews') then
    raise exception 'teacher_reviews missing from Realtime publication';
  end if;
  if has_table_privilege('authenticated', 'public.teacher_reviews', 'INSERT,UPDATE,DELETE') then
    raise exception 'authenticated browser write privileges unexpectedly granted';
  end if;
end;
$$;
rollback;
