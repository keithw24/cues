# Teacher-controlled sessions, and how vision follows them

This is the handoff between the dashboard (Evan), vision (Keith) and the database. It is merged
and live: migrations 003 to 017 are applied, and `./scripts/dev.sh` runs it by default. No service
credentials are shared with Evan or placed in the browser.

How it fits together now:

- **A teacher signs in and the dashboard finds their own station** (one persistent default station
  per account, created on first sign-in; see `notes/supabase.md`, migration 011).
- **The dashboard tells this laptop's vision which station it is** with `POST 127.0.0.1:8000/config`
  (loopback only). Vision reads and writes nothing until a station arrives. `CUES_STATION_ID` in the
  root `.env` *pins* vision to one station and refuses any other: leave it unset for normal use.
- **Only one camera can use a station at a time** (migration 017). A second camera is refused and
  paused, and the dashboard warns; see "One camera per station" in `notes/supabase.md`.
- **The teacher starts and ends sessions** from Session controls. Vision follows the station's
  active session, its activity and its revision (below).

Required files travel togetherRequired files travel together: `shared/contracts.py`, `flags.json`,
`vision/session_sync.py`, `vision/stages/s00_session.py`, `vision/activity_sync.py`,
`vision/events.py`, `vision/stages/s30_gestures.py`, `s35_raise_hand.py`,
`s50_status.py`, and `vision/watch.py`. Tests are in
`vision/tests/test_session_sync.py`; the frontend/SQL contract is documented in
`notes/web-session-controls.md`. No dependencies or activity model were added.

## Running vision

The normal way is `./scripts/dev.sh` (or `demo.sh`), which starts vision, the agent worker and the
dashboard with the session lifecycle on by default. To run vision alone, from the repo root with the
root `.env` supplying `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`:

```sh
uv sync
CUES_FLAG_VISION_SESSION_LIFECYCLE=1 \
CUES_FLAG_VISION_SUPABASE_EVENTS=1 \
CUES_FLAG_VISION_TASK_STATUS=1 \
CUES_FLAG_VISION_HANDS=1 \
CUES_FLAG_VISION_GESTURES=1 \
CUES_FLAG_VISION_RAISE_HAND=1 \
uv run uvicorn vision.app:app --host 127.0.0.1 --port 8000
```

Do not set `CUES_STATION_ID` (see above), and keep only one vision process per station.
`CUES_SESSION_ID` is not used for managed frames. Existing local model/template setup remains
necessary.

Alternatively use the `vision.watch --all-on` workflow with the lifecycle/emission
environment flags; omit `--task`, which would conflict with teacher ownership. Preserve the existing camera index, person tracking and local
expression settings. Don't use fake-camera output as evidence of real inference.

The root server defaults to one-second session polling. It acknowledges
configuration through service-only `report_station_session`. Failed reads/reports
or an expired seven-second lease (under the 10s one-camera writer lease) pause task evaluation (a busy laptop can stall a
poll for several seconds; the database still rejects writes for an ended session
or an old revision). No session and ended sessions also pause evaluation/writes.
A pause keeps each person's status; holds and timers skip the paused time. Camera preview remains local and available.
Only a new session/revision resets vision's task/hold/expression trackers; model and
camera data are not uploaded.

## Teacher account is separate

Whoever operates the teacher dashboard needs a Supabase Auth account; they sign in with their own
email and password (entered privately), and the dashboard creates and assigns their station. The
station's emitter uses its existing service credentials independently of that login. Teachers do
not need `station_teachers` rows provisioned by hand.

The dashboard's session controls are on by default (since 2026-11-14); `CUES_FLAG_WEB_SESSION_CONTROLS=0`
in `web/.env.local` turns them off, then restart the dashboard. Use `/dashboard`. `CUES_STATION_OVERRIDE` in
`web/.env.local` pins the dashboard to one station for dev/test only. The local video can be viewed
only from the station laptop at `http://127.0.0.1:8000/stream`; don't expose or tunnel it remotely.
The Supabase dashboard state can be observed on another laptop without video.

## Live verification checklist

- Confirm the station's `station_runtime` row updates once per second. Match its session
  UUID, revision and activity to `sessions`; the UI should show Activity synced.
  This label acknowledges configuration, not inference health.
- End the current session. Verify persisted `ended_at`, revision +1 and no active
  S1 session. It should show Waiting for station to stop, then Station idle.
  Task checks/state writes stop; local video may continue.
- Start an activity from the catalog. Verify a new UUID, revision 0, matching
  station acknowledgement and fresh `seat_state` rows with the same UUID,
  activity and `session_revision`. Do not fabricate scores for this check.
- Change to another catalog activity if one is provisioned and locally supported.
  Keep the UUID; increment revision and reset vision task progress. The hosted
  catalog has Raise your hand plus the built-in gestures (migration 014).
- Refresh the dashboard: session/activity must persist. Two tabs making requests
  from the same older revision must not both succeed; refresh the losing tab.
- Stop/disconnect the station: UI acknowledgement expires, task processing pauses
  after the lease, and saved session state remains. Reconnect and check recovery.
- Check a browser cannot write sessions/runtime directly or report station state.

The database rejects queued old/ended observations after teacher actions. Once
S1 is managed, reverting only the vision flag will not restore old unversioned
writes; coordinate rollback with Evan rather than disabling that protection.

Verified: migration and authorization checks on the deployed Supabase (rollback-only isolated
station), the database tests in `supabase/tests/`, and local unit and browser fixtures. Still to
verify on real hardware, with two laptops signed in as different teachers: camera inference under
session changes, teacher login and Realtime, and simultaneous independent-client actions. The
checklist is tracked in `notes/outstanding-work.md` (P0).
