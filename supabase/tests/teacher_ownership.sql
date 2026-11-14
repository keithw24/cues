-- Database-owner connection; all synthetic data rolls back.
begin;
insert into auth.users(id) values
 ('00000000-0000-4000-8000-0000000000a1'),
 ('00000000-0000-4000-8000-0000000000b1');
insert into public.teacher_profiles(user_id, phone_number) values
 ('00000000-0000-4000-8000-0000000000a1', '+1 (202) 555-0101');
do $$ begin
  if (select phone_number from public.teacher_profiles
      where user_id = '00000000-0000-4000-8000-0000000000a1') <> '+12025550101' then
    raise exception 'phone normalization failed';
  end if;
end $$;
insert into public.sessions(id, teacher_id) values
 ('00000000-0000-4000-8000-0000000000c1', '00000000-0000-4000-8000-0000000000a1');
-- Reuse an existing valid evaluation fixture shape, with owned synthetic identity.
insert into public.teacher_reviews(id,created_at,session_id,seat_id,activity_id,
 priority,evaluation,decision,rationale,evidence_used,status)
values ('00000000-0000-4000-8000-0000000000d1',now(),
 '00000000-0000-4000-8000-0000000000c1','ownership-test','raise_hand','normal',
 '{"session_id":"00000000-0000-4000-8000-0000000000c1","seat_id":"ownership-test","activity_id":"raise_hand","escalation":{"priority":"normal","should_evaluate":true},"progress":{"trend":"stalled"}}',
 'teacher_review_warranted','Synthetic ownership verification','["current_progress"]','pending');
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"00000000-0000-4000-8000-0000000000b1","role":"authenticated"}', true);
do $$ begin
  if exists(select 1 from public.teacher_profiles) then
    raise exception 'another teacher profile leaked';
  end if;
  if exists(select 1 from public.teacher_reviews where seat_id='ownership-test') then
    raise exception 'another teacher review leaked';
  end if;
  begin
    perform public.resolve_teacher_review('00000000-0000-4000-8000-0000000000d1','confirmed');
    raise exception 'cross-owner resolution allowed';
  exception when insufficient_privilege then null;
  end;
end $$;
select set_config('request.jwt.claims', '{"sub":"00000000-0000-4000-8000-0000000000a1","role":"authenticated"}', true);
select * from public.resolve_teacher_review('00000000-0000-4000-8000-0000000000d1','confirmed');
rollback;
