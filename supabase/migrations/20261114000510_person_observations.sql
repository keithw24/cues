-- Structured vision contract only. No frames, identities, or progress decisions.
begin;
alter table public.seat_state add column if not exists tracking_valid boolean;
-- Simulated hackathon station only. Metadata permits existing demo RLS to read
-- Keith's S1-P1..P4 state; metadata is never counted as an observed person.
insert into public.seats(id, station_id, side, display_name, is_simulated)
select 'S1-P' || n, 'S1', null, 'Person ' || n, true
from generate_series(1,4) n
where exists(select 1 from public.stations where id = 'S1')
on conflict(id) do nothing;
commit;
