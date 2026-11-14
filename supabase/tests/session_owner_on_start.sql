-- Run after migrations 006 and 007. Entire fixture rolls back.
-- Checks that a started session is owned by the caller and that its reviews become readable.
begin;
insert into auth.users(id) values
 ('8fbe1400-0000-4000-8000-0000000000a7'),
 ('8fbe1400-0000-4000-8000-0000000000b7');
insert into public.stations(id,name) values('__session_owner_check__','Isolated simulated check');
insert into public.seats(id,station_id,is_simulated) values('__session_owner_seat__','__session_owner_check__',true);
insert into public.station_teachers values('__session_owner_check__','8fbe1400-0000-4000-8000-0000000000a7');
set local role authenticated;
select set_config('request.jwt.claims','{"sub":"8fbe1400-0000-4000-8000-0000000000a7","role":"authenticated"}',true);
select set_config('cues.test_session_id',public.start_station_activity('__session_owner_check__','raise_hand',null,null)->>'id',true);
do $$
declare sid uuid:=current_setting('cues.test_session_id')::uuid; s jsonb;
begin
 s:=public.read_station_session('__session_owner_check__')->'session';
 assert s->>'teacher_id'='8fbe1400-0000-4000-8000-0000000000a7', 'session not owned by caller';
 assert exists(select 1 from public.sessions where id=sid), 'owner cannot read own session';
 -- An activity change keeps the owner.
 s:=public.start_station_activity('__session_owner_check__','raise_hand',sid,0);
 assert s->>'teacher_id'='8fbe1400-0000-4000-8000-0000000000a7', 'activity change lost the owner';
end $$;
set local role service_role;
insert into public.teacher_reviews(id,created_at,session_id,seat_id,activity_id,
 priority,evaluation,decision,rationale,evidence_used,status)
select '8fbe1400-0000-4000-8000-0000000000d7',now(),s.id,'__session_owner_seat__','raise_hand','normal',
 jsonb_build_object('session_id',s.id,'seat_id','__session_owner_seat__','activity_id','raise_hand',
  'escalation',jsonb_build_object('priority','normal','should_evaluate',true),
  'progress',jsonb_build_object('trend','stalled')),
 'teacher_review_warranted','Synthetic ownership verification','["current_progress"]','pending'
from public.sessions s where s.id=current_setting('cues.test_session_id')::uuid;
set local role authenticated;
do $$ begin
 assert exists(select 1 from public.teacher_reviews where id='8fbe1400-0000-4000-8000-0000000000d7'),
  'owner cannot read review for own session';
end $$;
select set_config('request.jwt.claims','{"sub":"8fbe1400-0000-4000-8000-0000000000b7","role":"authenticated"}',true);
do $$ begin
 assert not exists(select 1 from public.teacher_reviews where id='8fbe1400-0000-4000-8000-0000000000d7'),
  'review leaked to another teacher';
 begin
  perform public.start_station_activity('__session_owner_check__','raise_hand',null,null);
  raise exception 'non-member started a session';
 exception when insufficient_privilege then null; end;
end $$;
rollback;
