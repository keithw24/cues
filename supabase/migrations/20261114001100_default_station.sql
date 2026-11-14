-- One persistent default station per teacher account (1 teacher = 1 default station;
-- 1 station = many sessions over time). Requires migration 310 (station_teachers) and
-- 800 (pairing is unchanged and still adds non-default memberships).
--
-- The caller is always auth.uid(): the browser never supplies a teacher or station owner.
-- Existing stations, memberships, sessions and their owners are not changed. Only the new
-- is_default marker is added; the single-assignment teacher (Keith -> S1) is backfilled.
begin;

alter table public.station_teachers add column is_default boolean not null default false;

-- A teacher with exactly one existing assignment already has their default station.
-- Teachers with several assignments are never guessed at here.
update public.station_teachers st set is_default = true
where st.teacher_id in (
  select teacher_id from public.station_teachers group by teacher_id having count(*) = 1
);

-- At most one default per teacher. This is also what stops two concurrent first logins
-- from both creating a default.
create unique index station_teachers_one_default_per_teacher
  on public.station_teachers (teacher_id) where is_default;

create function public.get_or_create_my_default_station() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := auth.uid();
  sid text;
  owned integer;
  made boolean := false;
begin
  if uid is null or auth.role() is distinct from 'authenticated' then
    raise exception 'Authentication required' using errcode = '42501';
  end if;
  -- Serialize this teacher's calls so a double-click or two tabs cannot race.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('cues.default_station.' || uid::text, 0));

  select st.station_id into sid
    from public.station_teachers st where st.teacher_id = uid and st.is_default;

  if sid is null then
    select count(*), min(st.station_id) into owned, sid
      from public.station_teachers st where st.teacher_id = uid;
    if owned = 1 then
      -- Their only assignment is their station: adopt it rather than creating another.
      update public.station_teachers set is_default = true
        where teacher_id = uid and station_id = sid;
    else
      -- None (or several, with no default chosen): create their own station.
      -- Station numbering is global, so take a second lock (always after the first).
      perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('cues.station_ids', 0));
      select 'S' || (coalesce(max(substring(s.id from '^S([0-9]+)$')::integer), 0) + 1)
        into sid from public.stations s where s.id ~ '^S[0-9]{1,9}$';
      insert into public.stations(id, name) values (sid, 'Station ' || sid);
      -- Simulated demo person metadata, as for S1 (migration 510), so the existing
      -- read policy lets the dashboard show this station's people.
      insert into public.seats(id, station_id, side, display_name, is_simulated)
        select sid || '-P' || n, sid, null, 'Person ' || n, true
        from generate_series(1, 4) n on conflict (id) do nothing;
      insert into public.station_teachers(station_id, teacher_id, is_default)
        values (sid, uid, true);
      made := true;
    end if;
  end if;

  return jsonb_build_object(
    'station_id', sid,
    'name', (select s.name from public.stations s where s.id = sid),
    'created', made);
end $$;
revoke all on function public.get_or_create_my_default_station() from public, anon, service_role;
grant execute on function public.get_or_create_my_default_station() to authenticated;

commit;
