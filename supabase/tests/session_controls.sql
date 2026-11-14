-- Run through Supabase SQL Editor after migrations 003 and 005.
-- Entire fixture rolls back, including the identity (no credentials or email).
-- Never starts/ends S1 or changes its membership/observations.
begin;
insert into auth.users(id) values ('8fbe1400-0000-4000-8000-000000000005');
insert into public.stations(id,name) values('__session_control_check__','Isolated simulated check');
insert into public.seats(id,station_id,is_simulated) values('__session_control_seat__','__session_control_check__',true);
insert into public.station_teachers values('__session_control_check__','8fbe1400-0000-4000-8000-000000000005');
set local role authenticated;
select set_config('request.jwt.claim.sub','8fbe1400-0000-4000-8000-000000000005',true);
select set_config('cues.test_session_id',public.start_station_activity('__session_control_check__','raise_hand',null,null)->>'id',true);
do $$
declare sid uuid:=current_setting('cues.test_session_id')::uuid; s jsonb;
begin
 s:=public.read_station_session('__session_control_check__')->'session';
 assert s->>'id'=sid::text and (s->>'revision')::integer=0;
 begin
  perform public.start_station_activity('__session_control_check__','raise_hand',null,null);
  raise exception 'Duplicate start accepted';
 exception when serialization_failure then null; end;
 begin
  update public.sessions set current_activity_id='raise_hand' where id=sid;
  raise exception 'Direct session write accepted';
 exception when insufficient_privilege then null; end;
 begin
  perform public.report_station_session('__session_control_check__',sid,0,'raise_hand','ready',null,array['raise_hand']);
  raise exception 'Teacher station spoof accepted';
 exception when insufficient_privilege then null; end;
end $$;
set local role service_role;
select public.report_station_session('__session_control_check__',current_setting('cues.test_session_id')::uuid,0,'raise_hand','ready',null,array['raise_hand']);
insert into public.seat_state(seat_id,session_id,activity_id,status,session_revision)
 values('__session_control_seat__',current_setting('cues.test_session_id')::uuid,'raise_hand','in_progress',0);
set local role authenticated;
select public.end_station_session('__session_control_check__',current_setting('cues.test_session_id')::uuid,0);
do $$
begin
 assert public.read_station_session('__session_control_check__')->'session'='null'::jsonb;
 begin
  perform public.end_station_session('__session_control_check__',current_setting('cues.test_session_id')::uuid,0);
  raise exception 'Stale end accepted';
 exception when serialization_failure then null; end;
end $$;
set local role service_role;
do $$
begin
 begin
  insert into public.seat_state(seat_id,session_id,activity_id,status,session_revision)
   values('__session_control_seat__',current_setting('cues.test_session_id')::uuid,'raise_hand','done',0)
   on conflict(seat_id) do update set status=excluded.status;
  raise exception 'Ended observation accepted';
 exception when check_violation then null; end;
 begin
  insert into public.events(session_id,station_id,seat_id,type,activity_id,payload)
   values(current_setting('cues.test_session_id')::uuid,'__session_control_check__','__session_control_seat__','attempt_success','raise_hand','{"session_revision":0}');
  raise exception 'Ended event accepted';
 exception when check_violation then null; end;
end $$;
select public.report_station_session('__session_control_check__',current_setting('cues.test_session_id')::uuid,1,null,'idle',null,array['raise_hand']);
set local role authenticated;
do $$
begin
 assert public.read_station_session('__session_control_check__')->'station_runtime'->>'status'='idle';
end $$;
select set_config('request.jwt.claim.sub','8fbe1400-0000-4000-8000-000000000006',true);
do $$
begin
 assert not exists(select 1 from public.station_runtime where station_id='__session_control_check__');
 begin
  perform public.read_station_session('__session_control_check__');
  raise exception 'Other teacher read accepted';
 exception when insufficient_privilege then null; end;
end $$;
set local role anon;
do $$
begin
 begin
  perform public.read_station_session('__session_control_check__');
  raise exception 'Anonymous read accepted';
 exception when insufficient_privilege then null; end;
end $$;
rollback;
select 'PASS: authorized start/end, duplicate/stale rejection, scoped station acknowledgement, ended-write rejection, teacher/anonymous access boundaries; fixture rolled back' as verification;
