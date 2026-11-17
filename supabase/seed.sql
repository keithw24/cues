-- Synthetic demo data only. Safe to rerun; never reset existing seat progress.
begin;
insert into public.activities (id, name, check_type, keywords, no_progress_seconds, config)
values ('raise_hand', 'Raise your hand', 'rule', array['raise your hand', 'raise hand'], 30, '{}')
on conflict (id) do nothing;
-- Built-in gestures (same rows as migration 014).
insert into public.activities
  (id, name, check_type, keywords, success_threshold, review_threshold, no_progress_seconds, config)
values
  ('thumbs_up', 'Thumbs up', 'gesture', array['thumbs up', 'thumb'], 0.7, 0.5, 30, '{}'),
  ('open_palm', 'Open palm', 'gesture', array['open palm', 'stop', 'palm'], 0.7, 0.5, 30, '{}'),
  ('pointing', 'Pointing', 'gesture', array['pointing', 'point', 'select'], 0.7, 0.5, 30, '{}'),
  ('peace', 'Peace sign', 'gesture', array['peace', 'two fingers', 'peace sign'], 0.7, 0.5, 30, '{}'),
  ('fist', 'Fist', 'gesture', array['fist', 'done', 'ready'], 0.7, 0.5, 30, '{}')
on conflict (id) do nothing;
insert into public.stations (id, name) values ('S1', 'Demo station') on conflict (id) do nothing;
insert into public.seats (id, station_id, side, display_name, is_simulated)
values ('S1-L', 'S1', 'left', 'Left seat', true), ('S1-R', 'S1', 'right', 'Right seat', true)
on conflict (id) do nothing;
-- One seat per person id vision can issue (vision.people.MAX_PEOPLE = 6), as stations made
-- by get_or_create_my_default_station have.
insert into public.seats (id, station_id, side, display_name, is_simulated)
select 'S1-P' || n, 'S1', null, 'Person ' || n, true from generate_series(1, 6) n
on conflict (id) do nothing;
insert into public.sessions (id, current_activity_id)
values ('00000000-0000-4000-8000-000000000001', 'raise_hand') on conflict (id) do nothing;
insert into public.seat_state (seat_id, session_id, activity_id, status)
values
  ('S1-L', '00000000-0000-4000-8000-000000000001', 'raise_hand', 'idle'),
  ('S1-R', '00000000-0000-4000-8000-000000000001', 'raise_hand', 'idle')
on conflict (seat_id) do nothing;
commit;
