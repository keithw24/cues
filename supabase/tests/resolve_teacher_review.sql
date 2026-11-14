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


update public.seats set is_simulated=true where id='REVIEW-SQL-PRIVATE';
set local role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000099',true);
select set_config('request.jwt.claim.role','authenticated',true);
do $$
declare r public.teacher_reviews; original public.teacher_reviews; rejected boolean; a text;
begin
 select * into original from public.teacher_reviews where seat_id='REVIEW-SQL-DEMO';
 select * into strict r from public.resolve_teacher_review(original.id,'confirmed');
 assert r.status='confirmed' and r.resolved_at >= r.created_at;
 assert to_jsonb(r)-'status'-'resolved_at'=to_jsonb(original)-'status'-'resolved_at';
 foreach a in array array['confirmed','dismissed','invalid'] loop
 rejected:=false;
 begin perform public.resolve_teacher_review(original.id,a); exception when invalid_parameter_value then rejected:=true; end;
 assert rejected;
 end loop;
 rejected:=false;
 begin perform public.resolve_teacher_review('00000000-0000-0000-0000-000000000000','confirmed'); exception when no_data_found then rejected:=true; end;
 assert rejected;
 rejected:=false;
 begin update public.teacher_reviews set rationale='changed' where id=original.id; exception when insufficient_privilege then rejected:=true; end;
 assert rejected;
 select * into strict r from public.resolve_teacher_review('00000000-0000-0000-0000-000000000102','dismissed');
 assert r.status='dismissed' and r.resolved_at is not null;
end; $$;
reset role;
set local role anon;
do $$ declare rejected boolean:=false; begin
 begin perform public.resolve_teacher_review('00000000-0000-0000-0000-000000000101','confirmed'); exception when insufficient_privilege then rejected:=true; end;
 assert rejected;
end; $$;
rollback;
