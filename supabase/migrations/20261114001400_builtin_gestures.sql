-- The built-in gestures vision can detect without any recording, so a teacher can pick
-- them as an activity. Values mirror vision/activities.json (a test keeps them in step).
-- Idempotent: an existing row (for example raise_hand) is never overwritten.
begin;
insert into public.activities
  (id, name, check_type, keywords, success_threshold, review_threshold, no_progress_seconds, config)
values
  ('thumbs_up', 'Thumbs up', 'gesture', array['thumbs up', 'thumb'], 0.7, 0.5, 30, '{}'),
  ('open_palm', 'Open palm', 'gesture', array['open palm', 'stop', 'palm'], 0.7, 0.5, 30, '{}'),
  ('pointing', 'Pointing', 'gesture', array['pointing', 'point', 'select'], 0.7, 0.5, 30, '{}'),
  ('peace', 'Peace sign', 'gesture', array['peace', 'two fingers', 'peace sign'], 0.7, 0.5, 30, '{}'),
  ('fist', 'Fist', 'gesture', array['fist', 'done', 'ready'], 0.7, 0.5, 30, '{}')
on conflict (id) do nothing;
commit;
