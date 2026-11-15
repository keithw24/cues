# Teacher session controls

Start activity and End session use saved Supabase state, never a browser-only
session. `web.session_controls` defaults on (since 2026-11-14; `=0` turns it off). Migration 003 and migration 005
were applied to the team's Supabase project on November 14, 2026. The original
S1 UUID was preserved, revision remains 0, and its session has not been ended.

## Contract and security

- `read_station_session(p_station_id)` returns `session` (active or null),
  `latest_session`, `station_runtime`, and the existing activity catalog. Once a
  station reports its capabilities, the catalog is limited to locally known IDs.
- `start_station_activity(p_station_id, p_activity_id, p_expected_session_id,
  p_expected_revision)` returns the committed session. Changing an active task
  preserves its UUID and increments revision. Starting an empty station creates
  a database-generated UUID with revision 0.
- `end_station_session(p_station_id, p_expected_session_id,
  p_expected_revision)` persists `ended_at` and increments revision.
- Supabase Auth users need an administrator-provisioned
  `station_teachers(station_id, teacher_id)` membership. There were no Auth users
  or memberships at deployment; no teacher credentials were created by the agent.
- Station row locks serialize actions, including starts with no existing row.
  A partial unique index permits one active session per station. Stale UUID or
  revision requests fail instead of creating another session or changing a newer
  task. Ambiguous action failures require explicit Refresh session before retry.
- Browsers have no direct session or runtime writes. Teacher RPCs enforce station
  membership. Station acknowledgement is service-only; teachers cannot spoof it.
  Service credentials stay in the station's root `.env`, never `NEXT_PUBLIC_*`.

## UI and realtime

Manage activity contains the compact activity selector, Start activity, End
session, Refresh session and sign-out. Supabase Auth persists the teacher login.
Actions disable conflicting controls while saving. Header and video caption use
only the saved session response. Failed/invalid responses retain the previous
confirmed state and show a sanitized error; refresh reconciles ambiguous outcomes.

Subscriptions to `sessions` and `station_runtime`, reconnect reads, online recovery
and a 15-second resync update other clients. Reads are coalesced; heartbeat reads
do not flash the saving state or disable controls. A display clock expires old
acknowledgements; it does not make task-progress decisions.

- Waiting for the camera to sync: saved active configuration has no matching fresh
  acknowledgement.
- Activity synced: fresh station report matches session UUID, revision and task.
  This acknowledges configuration, not proof that a camera/model is working.
- Waiting for the camera to stop: End is saved, but the exact ended UUID/revision has
  not been acknowledged idle.
- Camera idle: a fresh idle acknowledgement matches the saved ended session.
- Activity unavailable on the camera: station reports an unsupported activity.

## Vision integration

See [Keith's handoff](session-lifecycle.md). Under the separate default-off
`vision.session_lifecycle` flag, vision polls the authoritative station session
once a second and reports configuration through `report_station_session`. Each
frame pins immutable UUID/activity/revision. Switching/restarting a task resets
vision's trackers. End, failed reads/acknowledgements, unknown tasks and leases
older than three seconds pause task checks and session observation writes. The
local camera preview and person perception can continue. `--task` cannot override
a managed session. The legacy fixed `CUES_SESSION_ID` path remains when off.

Migration 005 rejects stale/ended/mismatched seat-state and perception-event
writes once the station is managed. `SeatState.session_revision` and perception
`Event.payload.session_revision` carry the saved revision. Queued observations
cannot overwrite newer session state. `stations.session_managed` stays false
until a successful teacher Start/End, so deploying the schema alone does not
break Keith's existing emitter. After activation, turning off the vision flag
alone intentionally does not disable the database guard or allow legacy writes.

## Verification and remaining rollout

Passed: frontend unit tests, lint, production build, isolated browser fixtures for
saved selection/header/End/refresh persistence, ready/idle realtime messages,
loading/errors and mobile overflow; Python vision/shared tests; PostgreSQL checks
for migration application, stale/duplicate requests, scoped access and stale
observation rejection. Browser fixtures mock Auth and transport and are distinct
from deployed authorization verification.

`supabase/tests/session_controls.sql` also passed on the real project using role
switches and a transaction-only simulated station/identity. It rolls back all
fixture records and never starts/ends S1. Verified afterward: no test records,
no teacher accounts, no station acknowledgements, S1 unchanged and unmanaged.
These checks do not establish real independent-client concurrency, teacher login,
authorized Realtime delivery or Keith's hardware behavior.

Remaining:
1. Create the teacher Auth user with the actual dashboard operator's email and
   their privately entered password. Grant only that user's S1 membership.
2. Keith loads this change set from the `evan` branch on his station and restarts with the
   lifecycle/emission/task flags. Do not run a second S1 emitter on Evan's laptop.
3. Enable the web flag and rebuild. The dashboard uses the signed-in teacher's default
   station (see "Default station per teacher" below); no station id is configured. Verify teacher login,
   a fresh station acknowledgement, Start/new UUID, task switch, End/idle and
   refresh in the actual dashboard. Check a second stale tab is rejected.
4. Michelle's future live progress/routing consumer must observe session revision
   and call its existing reset hook on a restart, and stop on an ended session.
   No ProgressEvaluator algorithm, routing or review semantics changed here.
5. Keith/Evan/Michelle contract review is still required before a requested merge.

Evan requested a commit/push of the accumulated app work to `evan`. No merge to
`main` is included. The feature has defaulted on since 2026-11-14.

## Default station per teacher

One teacher account has one persistent default station; a station has many sessions over
time. After sign-in the dashboard calls `get_or_create_my_default_station()` (migration
`20261114001100_default_station.sql`), which uses only `auth.uid()`:

- an existing default is returned;
- a teacher whose only assignment is one station (Keith → S1) gets that station as their default;
- otherwise a new station (`S2`, `S3`, …) with four simulated person slots is created and
  assigned to them, once, even if two tabs call at the same time.

Session controls, the activity picker, seats and observations, and teacher reviews are all
scoped to that station. Start Session still calls `start_station_activity`, which creates a
new session owned by `auth.uid()`; it never creates a station. The dashboard has no pairing-code
screen: each teacher uses their own default station.

The vision laptop follows the same station without configuration: once the teacher is
signed in, the dashboard sends the resolved station to the local vision service
(`POST 127.0.0.1:8000/config`, flags `web.vision_station_config` / `vision.station_config`).
Do not set `CUES_STATION_ID` in the root `.env` unless you mean to pin vision to one
station: a pinned laptop refuses any other station. Each laptop needs
`CUES_FLAG_VISION_SESSION_LIFECYCLE=1` to follow its own station's session.
`CUES_STATION_OVERRIDE` in `web/.env.local` pins the dashboard to one station for dev/test only.
