-- One camera per station.
--
-- Seat rows are named by station and person number (S1-P1), so two cameras working for the
-- same station overwrite each other's rows and show up as phantom people. Each camera
-- process now claims its station with a random writer id; the claim is a lease that has to be
-- renewed (vision does it about once a second). While the holder's lease is fresh, any other
-- camera is refused, and the refusal is recorded so the dashboard can warn. When the holder
-- stops (it releases at once) or crashes (the lease expires after the TTL), another camera
-- takes over. Requires 310 (station_teachers).
begin;

create table public.station_writers (
  station_id text primary key references public.stations(id) on delete cascade,
  writer_id uuid not null,
  seen_at timestamptz not null default now(),   -- the holder's last renewal
  contested_at timestamptz                       -- the last time another camera was refused
);
alter table public.station_writers enable row level security;
revoke all on public.station_writers from anon, authenticated;
grant all on public.station_writers to service_role;
-- Teachers of the station read it, only to warn that a second camera is being refused.
grant select on public.station_writers to authenticated;
create policy teacher_writer_read on public.station_writers for select to authenticated
  using (exists (select 1 from public.station_teachers t
                 where t.station_id = station_writers.station_id and t.teacher_id = auth.uid()));

create function public.claim_station_writer(
  p_station_id text, p_writer_id uuid, p_ttl_seconds integer default 10
) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  r public.station_writers;
  ttl interval := pg_catalog.make_interval(secs => greatest(coalesce(p_ttl_seconds, 10), 3));
begin
  if p_station_id is null or p_writer_id is null then
    raise exception 'Station and writer are required' using errcode = '22023';
  end if;
  if not exists (select 1 from public.stations where id = p_station_id) then
    raise exception 'Station unavailable' using errcode = '22023';
  end if;
  -- One statement, so concurrent claims serialize on the row: exactly one holder.
  insert into public.station_writers as w (station_id, writer_id, seen_at)
    values (p_station_id, p_writer_id, pg_catalog.clock_timestamp())
  on conflict (station_id) do update set
    writer_id = case
      when w.writer_id = excluded.writer_id
        or w.seen_at < pg_catalog.clock_timestamp() - ttl then excluded.writer_id
      else w.writer_id end,
    seen_at = case
      when w.writer_id = excluded.writer_id
        or w.seen_at < pg_catalog.clock_timestamp() - ttl then pg_catalog.clock_timestamp()
      else w.seen_at end,
    contested_at = case
      when w.writer_id = excluded.writer_id
        or w.seen_at < pg_catalog.clock_timestamp() - ttl then w.contested_at
      else pg_catalog.clock_timestamp() end
  returning * into r;
  return jsonb_build_object(
    'granted', r.writer_id = p_writer_id,
    'held_seconds_ago', extract(epoch from pg_catalog.clock_timestamp() - r.seen_at));
end $$;

-- A camera that stops hands the station over at once instead of making the next one wait.
create function public.release_station_writer(p_station_id text, p_writer_id uuid) returns void
language plpgsql security definer set search_path = '' as $$
begin
  update public.station_writers
    set seen_at = 'epoch'::timestamptz
    where station_id = p_station_id and writer_id = p_writer_id;
end $$;

revoke all on function public.claim_station_writer(text, uuid, integer)
  from public, anon, authenticated;
revoke all on function public.release_station_writer(text, uuid) from public, anon, authenticated;
grant execute on function public.claim_station_writer(text, uuid, integer) to service_role;
grant execute on function public.release_station_writer(text, uuid) to service_role;

commit;
