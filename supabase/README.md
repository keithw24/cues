# Cues database

`migrations/20261114000100_initial_schema.sql` implements PRD §17.3 without changing
the shared table/event fields. Apply it once in a new Supabase project's SQL
Editor, then run `seed.sql`. The seed uses only simulated data and can be rerun
without resetting existing rows. Do not reapply the migration to an existing schema.

All nine tables have Row Level Security enabled. The publishable key can read
simulated seats and their associated station, session, activity and seat state.
These demo rows are publicly readable: use no real student data or private notes
in them. Browser writes are denied. Events, alerts, interventions and support
preferences are server-only. Teacher authentication and authorized alert reads
must be implemented before connecting the teacher decision workflow.

`seat_state` is included in the `supabase_realtime` publication. The frontend must
fetch initial state and subscribe to Postgres Changes; configuring environment
variables alone does not connect the existing Next.js scaffold.

Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` in
`web/.env.local`. Privileged clients use the root `.env` with `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY` (as consumed by the current vision client). Never put
a service-role or secret key in browser variables. Vision cloud event writes also
require the `vision.supabase_events` flag; leave it off until integration is verified.

In the SQL Editor, verify tables, RLS, demo rows and publication membership:

```sql
select tablename, rowsecurity from pg_tables where schemaname = 'public' order by tablename;
select * from public.seat_state;
select tablename from pg_publication_tables where pubname = 'supabase_realtime';
begin;
set local role anon;
select * from public.seats;
select * from public.seat_state;
rollback;
```

Once a dashboard subscribes, update a simulated seat through the Table Editor
and verify that its card changes without refreshing. Camera, model, agent,
teacher approval and Photon verification are separate integration work.

Verified against the hosted `cues` project on November 13, 2026:

- All nine tables have RLS enabled.
- The configured publishable key reads two seats, two seat-state rows and the
  associated station, activity and session. Seeded status is `idle`, matching
  the existing vision status vocabulary.
- Anonymous INSERT/UPDATE privileges on `seat_state` are absent; reading alerts
  through the publishable key is denied.
- A Postgres Changes subscription using the publishable key received a real
  `seat_state` UPDATE after changing a simulated row's timestamp in the SQL Editor.

The dashboard itself remains the Next.js scaffold; this verification tests the
database API and realtime delivery, not a dashboard card.
