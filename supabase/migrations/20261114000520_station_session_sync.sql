-- Session control -> vision acknowledgement and stale-write protection.
begin;
alter table public.stations add column session_managed boolean not null default false;
alter table public.seat_state add column session_revision integer check (session_revision >= 0);
create table public.station_runtime (
  station_id text primary key references public.stations(id),
  session_id uuid references public.sessions(id),
  activity_id text,
  revision integer check (revision >= 0),
  status text not null check (status in ('ready','idle','error')),
  error text check (error is null or error = 'unsupported_activity'),
  supported_activity_ids text[] not null default '{}',
  updated_at timestamptz not null default now()
);
alter table public.station_runtime enable row level security;
revoke all on public.station_runtime from public, anon, authenticated;
grant select on public.station_runtime to authenticated;
grant all on public.station_runtime to service_role;
create policy teacher_runtime_read on public.station_runtime for select to authenticated
 using (exists(select 1 from public.station_teachers t where t.station_id=station_runtime.station_id and t.teacher_id=auth.uid()));
alter publication supabase_realtime add table public.station_runtime;

create function public.report_station_session(p_station_id text, p_session_id uuid,
 p_revision integer, p_activity_id text, p_status text, p_error text,
 p_supported_activity_ids text[]) returns void
language plpgsql security definer set search_path='' as $$
declare s public.sessions;
begin
 perform 1 from public.stations where id=p_station_id for share;
 if not found then raise exception 'Station unavailable'; end if;
 if p_session_id is not null then
   select * into s from public.sessions where id=p_session_id and station_id=p_station_id for share;
   if s.id is null or s.revision is distinct from p_revision then
     raise exception 'Stale station acknowledgement' using errcode='40001';
   end if;
 end if;
 if p_status not in ('ready','idle','error') or p_status is null then raise exception 'Invalid station state'; end if;
 if p_status='ready' and (s.id is null or s.ended_at is not null or p_activity_id is distinct from s.current_activity_id or p_activity_id is null) then
   raise exception 'Invalid active station acknowledgement';
 end if;
 if p_status='idle' and (p_activity_id is not null or (s.id is not null and s.ended_at is null and s.current_activity_id is not null)) then
   raise exception 'Invalid idle station acknowledgement';
 end if;
 if p_session_id is null and exists(select 1 from public.sessions where station_id=p_station_id and ended_at is null) then
   raise exception 'Active session exists' using errcode='40001';
 end if;
 insert into public.station_runtime(station_id,session_id,revision,activity_id,status,error,supported_activity_ids,updated_at)
 values(p_station_id,p_session_id,p_revision,p_activity_id,p_status,p_error,coalesce(p_supported_activity_ids,'{}'),clock_timestamp())
 on conflict(station_id) do update set session_id=excluded.session_id,revision=excluded.revision,
  activity_id=excluded.activity_id,status=excluded.status,error=excluded.error,
  supported_activity_ids=excluded.supported_activity_ids,updated_at=excluded.updated_at;
end $$;
revoke all on function public.report_station_session(text,uuid,integer,text,text,text,text[]) from public,anon,authenticated;
grant execute on function public.report_station_session(text,uuid,integer,text,text,text,text[]) to service_role;

create or replace function public.read_station_session(p_station_id text) returns jsonb
language plpgsql security definer set search_path='' as $$
begin
 perform public.require_station_teacher(p_station_id);
 return jsonb_build_object(
  'session',(select to_jsonb(s) from public.sessions s where s.station_id=p_station_id and s.ended_at is null),
  'latest_session',(select to_jsonb(s) from public.sessions s where s.station_id=p_station_id order by s.started_at desc,s.id desc limit 1),
  'station_runtime',(select to_jsonb(r) from public.station_runtime r where r.station_id=p_station_id),
  'activities',coalesce((select jsonb_agg(jsonb_build_object('id',a.id,'name',a.name) order by a.name)
    from public.activities a where not exists(select 1 from public.station_runtime where station_id=p_station_id)
      or a.id=any((select supported_activity_ids from public.station_runtime where station_id=p_station_id)::text[])), '[]'::jsonb)
 );
end $$;

create or replace function public.start_station_activity(p_station_id text,p_activity_id text,
 p_expected_session_id uuid,p_expected_revision integer) returns jsonb
language plpgsql security definer set search_path='' as $$
declare s public.sessions;
begin
 perform public.require_station_teacher(p_station_id);
 perform 1 from public.stations where id=p_station_id for update;
 if not found then raise exception 'Station unavailable'; end if;
 if not exists(select 1 from public.activities where id=p_activity_id) then raise exception 'Activity unavailable'; end if;
 if exists(select 1 from public.station_runtime where station_id=p_station_id)
   and not exists(select 1 from public.station_runtime where station_id=p_station_id and p_activity_id=any(supported_activity_ids)) then
   raise exception 'Activity unavailable on station';
 end if;
 select * into s from public.sessions where station_id=p_station_id and ended_at is null for update;
 if s.id is distinct from p_expected_session_id or (s.id is not null and s.revision is distinct from p_expected_revision) then
   raise exception 'Session changed; refresh before acting' using errcode='40001';
 end if;
 if s.id is null then
   insert into public.sessions(station_id,current_activity_id) values(p_station_id,p_activity_id) returning * into s;
 else
   update public.sessions set current_activity_id=p_activity_id, revision=revision+1 where id=s.id returning * into s;
 end if;
 update public.stations set session_managed=true where id=p_station_id;
 return to_jsonb(s);
end $$;

create or replace function public.end_station_session(p_station_id text,p_expected_session_id uuid,p_expected_revision integer) returns jsonb
language plpgsql security definer set search_path='' as $$
declare s public.sessions;
begin
 perform public.require_station_teacher(p_station_id);
 perform 1 from public.stations where id=p_station_id for update;
 if not found then raise exception 'Station unavailable'; end if;
 update public.sessions set ended_at=clock_timestamp(),revision=revision+1
  where id=p_expected_session_id and station_id=p_station_id and ended_at is null and revision=p_expected_revision returning * into s;
 if s.id is null then raise exception 'Session changed; refresh before acting' using errcode='40001'; end if;
 update public.stations set session_managed=true where id=p_station_id;
 return to_jsonb(s);
end $$;

create function public.guard_managed_observation() returns trigger
language plpgsql security definer set search_path='' as $$
declare v_station text; managed boolean; s public.sessions; v_revision text;
begin
 if TG_TABLE_NAME='events' then
   if NEW.type not in ('attempt_success','attempt_miss','review_needed','no_progress','tracking_lost','expression_context') then return NEW; end if;
 end if;
 select station_id into v_station from public.seats where id=NEW.seat_id;
 if TG_TABLE_NAME='events' then v_station=NEW.station_id; end if;
 if v_station is null then select station_id into v_station from public.sessions where id=NEW.session_id; end if;
 select session_managed into managed from public.stations where id=v_station for share;
 if managed is not true then return NEW; end if;
 select * into s from public.sessions where id=NEW.session_id and station_id=v_station for share;
 if TG_TABLE_NAME='events' then v_revision=NEW.payload->>'session_revision'; else v_revision=NEW.session_revision::text; end if;
 if s.id is null or s.ended_at is not null or NEW.activity_id is distinct from s.current_activity_id
    or v_revision is distinct from s.revision::text
    or not exists(select 1 from public.seats where id=NEW.seat_id and station_id=v_station) then
   raise exception 'Observation does not match active station session' using errcode='23514';
 end if;
 return NEW;
end $$;
revoke all on function public.guard_managed_observation() from public,anon,authenticated;
create trigger managed_seat_state before insert or update on public.seat_state for each row execute function public.guard_managed_observation();
create trigger managed_perception_event before insert on public.events for each row execute function public.guard_managed_observation();
commit;
