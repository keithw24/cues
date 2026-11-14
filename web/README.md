# Cues teacher dashboard

Read-only seat overview built with Next.js. It loads seats, activities, stations
and seat state using the Supabase publishable key, then refreshes on `seat_state`
Postgres Changes. The frontend's status vocabulary follows `shared/contracts.py`;
tests consume the canonical fixtures. No camera data, expression labels, private
events or alerts are requested. Task selection and teacher decisions are future work.

## Run

```bash
cd web
npm ci
cp -n .env.example .env.local
```

Fill in `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` in
`.env.local`, then set `CUES_FLAG_WEB_DASHBOARD=1` and run `npm run dev`. Open
http://localhost:3000. Never use a service-role or secret key in the web environment.

`web.dashboard` defaults off. The server resolves flags before importing the
dashboard; off shows a static Cues page without connecting to Supabase. Overrides
accept only `1`, `true`, `0`, `false`; `CUES_FLAG_WEB_DASHBOARD` wins over
`NEXT_PUBLIC_CUES_FLAG_WEB_DASHBOARD`. Restart after editing `.env.local`. In a
production build, flags and public configuration are evaluated at build time;
rebuild when changing them.

Apply database migrations in order before seeding (see `../supabase/README.md`).
Existing projects should apply `20261114000200_align_demo_activity.sql` to align
the original demo activity with the newly merged shared contract.

## Behavior and verification

- Loading and empty states never substitute fabricated seat data.
- Read failures or disconnected realtime retain the last snapshot with a warning.
- Reconnect reloads the full snapshot so changes missed while disconnected appear.
- Missing state is “Awaiting observation”; tracking loss is “Tracking paused”.
- Match score is displayed as a value from 0 to 1, never a probability. A missing
  score or lost tracking displays a dash. Observation timestamps are local browser time.
- Only `seat_state` is published initially; activity/seat metadata is refetched on
  state events or reconnect, rather than independently streamed.

```bash
npm run lint
npm test          # Node 22.18+; built-in TypeScript stripping
npm run build
```

Manual acceptance: update simulated `S1-L` from `idle` to `done` in Supabase's
Table Editor. Its card must show “Complete” without refreshing; restore `idle`
afterward. Disconnect networking to check the warning and reconnect to resync.
Set the feature flag to `0`, restart, and verify no dashboard data requests occur.

Verified November 13, 2026: lint and nine automated tests passed; production
builds passed with the dashboard both off and on. The flag-off production route
returned HTTP 200 with only the static fallback. In Safari, both simulated seats
loaded and the left seat changed from “Ready to begin” to “Complete” after a
Supabase update without refreshing. The seat was restored to `idle` afterward.
Desktop layout and single-column high-zoom reflow were inspected in the native
browser; a separate 390px mobile viewport and browser offline simulation remain
manual checks. Recovery and retained-snapshot behavior are covered by unit tests.
