# Keith: teacher-controlled session handoff

The new code is ready locally and Supabase migrations 003/005 are deployed.
**Use the session implementation from Evan's `evan` branch.** Review and load
that change set through the team branch workflow before restarting; pulling
`main` alone will not include it until it has been integrated. No service credentials need to be shared with
Evan or placed in the browser.

Required files travel together: `shared/contracts.py`, `flags.json`,
`vision/session_sync.py`, `vision/stages/s00_session.py`, `vision/activity_sync.py`,
`vision/events.py`, `vision/stages/s30_gestures.py`, `s35_raise_hand.py`,
`s50_status.py`, and `vision/watch.py`. Tests are in
`vision/tests/test_session_sync.py`; the frontend/SQL contract is documented in
`web/SESSION_CONTROLS.md`. No dependencies or activity model were added.

## Restart the existing S1 emitter

Stop the previous S1 emitter first; keep only one running process. On Keith's
station, the existing root `.env` must supply `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY`. The session now comes from Supabase by station;
`CUES_SESSION_ID` is not used for managed frames. Existing local model/template
setup remains necessary.

From the updated repository root:

```sh
uv sync
CUES_STATION_ID=S1 \
CUES_FLAG_VISION_SESSION_LIFECYCLE=1 \
CUES_FLAG_VISION_SUPABASE_EVENTS=1 \
CUES_FLAG_VISION_TASK_STATUS=1 \
CUES_FLAG_VISION_HANDS=1 \
CUES_FLAG_VISION_GESTURES=1 \
CUES_FLAG_VISION_RAISE_HAND=1 \
uv run uvicorn vision.app:app --host 127.0.0.1 --port 8000
```

Alternatively use the configured `vision.watch --all-on` workflow with the
lifecycle/emission environment flags; omit `--task`, which would conflict with
teacher ownership. Preserve the existing camera index, person tracking and local
expression settings. Don't use fake-camera output as evidence of real inference.

The root server defaults to one-second session polling. It acknowledges
configuration through service-only `report_station_session`. Failed reads/reports
or an expired three-second lease pause task evaluation. No session and ended
sessions also pause evaluation/writes. Camera preview remains local and available.
A new session/revision resets vision's task/hold/expression trackers; model and
camera data are not uploaded.

## Teacher account is separate

Whoever operates the teacher dashboard needs a Supabase Auth account. Use Keith's
email only if Keith is the dashboard operator. The operator enters the password
privately. After account creation, Evan provisions the exact Auth UUID in
`station_teachers` for S1. The station's emitter uses its existing service
credentials independently of that login.

Once Keith is running the new code and the teacher is provisioned, enable
`CUES_FLAG_WEB_SESSION_CONTROLS=1` with `CUES_STATION_ID=S1` in `web/.env.local`,
then rebuild/restart the dashboard. Registry defaults stay off until verified.
Use `/dashboard` → Manage activity. The local video can be viewed only from the
station laptop at `http://127.0.0.1:8000/stream`; don't expose/tunnel it remotely.
The Supabase dashboard state can be observed on another laptop without video.

## Live verification checklist

- Confirm an S1 `station_runtime` row updates once per second. Match its session
  UUID, revision and activity to `sessions`; the UI should show Activity synced.
  This label acknowledges configuration, not inference health.
- End the current session. Verify persisted `ended_at`, revision +1 and no active
  S1 session. It should show Waiting for station to stop, then Station idle.
  Task checks/state writes stop; local video may continue.
- Start an activity from the catalog. Verify a new UUID, revision 0, matching
  station acknowledgement and fresh `seat_state` rows with the same UUID,
  activity and `session_revision`. Do not fabricate scores for this check.
- Change to another catalog activity if one is provisioned and locally supported.
  Keep the UUID; increment revision and reset vision task progress. Current hosted
  catalog contains only Raise your hand; no extra activities were invented.
- Refresh the dashboard: session/activity must persist. Two tabs making requests
  from the same older revision must not both succeed; refresh the losing tab.
- Stop/disconnect the station: UI acknowledgement expires, task processing pauses
  after the lease, and saved session state remains. Reconnect and check recovery.
- Check a browser cannot write sessions/runtime directly or report station state.

The database rejects queued old/ended observations after teacher actions. Once
S1 is managed, reverting only the vision flag will not restore old unversioned
writes; coordinate rollback with Evan rather than disabling that protection.

Already verified: migration and authorization checks on deployed Supabase with a
rollback-only isolated simulated station, and local unit/browser fixtures. Still
unverified: Keith's real restart, camera inference, teacher login/Realtime and
simultaneous independent-client actions. The app work is being committed and pushed to `evan` at Evan's request. No merge
to `main` is part of this handoff.
