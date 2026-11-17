-- Vision follows up to six people per camera (vision.people.MAX_PEOPLE). A station has one
-- seat row per person id it can issue, because the observation guard refuses rows for a seat
-- that does not exist, so give every station seats 5 and 6 and make new stations with six.
-- Seats are simulated person metadata only (no names, no identities), as in migrations 510
-- and 1100. Existing stations, sessions and rows are not changed.
begin;

insert into public.seats(id, station_id, side, display_name, is_simulated)
select s.id || '-P' || n, s.id, null, 'Person ' || n, true
from public.stations s, generate_series(5, 6) n
on conflict (id) do nothing;

create or replace function public.get_or_create_my_default_station() returns jsonb
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
        from generate_series(1, 6) n on conflict (id) do nothing;
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
commit;
