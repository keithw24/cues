# Local startup

Use Python 3.11 with uv, Node 22+ and npm, a Logitech camera with OS camera
permission, and configured hosted Supabase/Spectrum projects.

```bash
uv sync
npm --prefix web ci
npm --prefix cues ci
./scripts/dev.sh
# Short presentation timings:
./scripts/demo.sh
```

Both wrappers use scripts/run-stack.sh and the same agent.dev supervisor to start
vision on port 8000, agent.worker, and Next.js on port 3000.
Dev uses the existing normal runtime defaults (4-second progress window,
5-second minimum observation, 10-second normal and 15-second prolonged stall).
Demo selects the existing DEMO_PROGRESS_WINDOW_SECONDS and DEMO_ESCALATION_CONFIG:
2-second window/minimum, 4-second normal, 5-second expression-assisted and
6-second prolonged stall. Expression persistence remains five seconds. Demo
timing is for presentation speed, not a classroom recommendation.
Component logs are prefixed. Ctrl-C/SIGTERM stops all isolated process groups,
with SIGKILL for surviving groups after a shared five-second grace period,
even if their direct child has exited. Direct children are reaped. A component exit stops
the stack. Photon runs on demand; no separate Photon daemon is started.
The launcher does not apply migrations or create demo data.

## Environment

Root `.env` (backend only; never commit credentials):

| Variable | Use |
|---|---|
| `SUPABASE_URL` | Required project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Required privileged server credential |
| `GROQ_API_KEY` | Required demo model key |
| `CUES_SESSION_ID` | Required existing session UUID |
| `CUES_STATION_ID` | Optional station, default S1 |
| `CUES_CAMERA_INDEX` | Optional camera index, default 0; USB often 1 |
| `CUES_CAMERA` | Optional `fake` for camera-free startup |

Both modes default hands, faces, gestures, raise-hand, expression, task-status,
Supabase publication and activity-sync flags ON. Shell values take priority over
root .env; saved nonempty root .env flag values take priority over defaults.
For example:

```bash
CUES_FLAG_VISION_EXPRESSION=0 ./scripts/demo.sh
CUES_CAMERA=fake ./scripts/dev.sh
CUES_MODE=recognize ./scripts/demo.sh
```
For the current Logitech setup use `CUES_CAMERA_INDEX=1`; other machines may need
0 or 2. Optional `CUES_MODE=recognize` is preserved but never forced.
Weights may download on first use. Fake frames do not simulate student progress.

`web/.env.local`: browser-safe `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`; enable `CUES_FLAG_WEB_DASHBOARD=1`.
Consult `web/README.md` for available teacher review UI flags/authentication.
The current web checkout exposes only the dashboard flag; activity writes and
persistent review/RPC controls remain frontend integration gaps. There are no
implemented teacher-review UI flags to enable here.
Never expose service-role, Groq, or Spectrum credentials as `NEXT_PUBLIC_*`.

`cues/.env`: backend-only `SPECTRUM_PROJECT_ID`, `SPECTRUM_PROJECT_SECRET`,
`SPECTRUM_TEACHER_PHONE` is test-only; optional `SPECTRUM_SENDER_PHONE` selects the line.
Testing = static mode 1: `CUES_USE_STATIC_TEACHER_PHONE=1 ./scripts/dev.sh` uses
the env destination. Actual demo = dynamic mode 0: `./scripts/demo.sh` forces 0,
even if the shell or env requests 1. Dynamic mode ignores the static destination
and resolves review.session_id → sessions.teacher_id → teacher_profiles.phone_number.
Missing owner/profile/phone fails notification clearly and retains the pending review.
There is no static fallback. Add the opted-in profile destination to active Spectrum Users.
The sender loads this file relative to its module, independent of working directory.
Missing/incomplete Spectrum configuration produces a warning and disables the
notifier for that worker; persistence and review processing can still run.
Restart after adding notification configuration.

## Database and demo prerequisites

Apply migrations 001 through 006 in filename order; see `supabase/README.md`.
Migration 004 is deployed: authenticated resolve_teacher_review exists with
demo-only authorization. Migration 006 is implemented locally but **NOT deployed**:
it adds teacher_profiles, sessions.teacher_id, owner-only review reads/resolution,
and the schema required for dynamic teacher-profile Photon routing. It must be deployed before
dynamic notifications/profile UI. Historical sessions remain unowned; assign
ownership through a trusted backend/admin, never an arbitrary browser claim.
The current hosted project already has `seat_state.tracking_valid`,
`teacher_reviews`, authenticated `resolve_teacher_review` RPC, and Realtime
publication membership. Do not reapply initial schema to that project.

Provision the session and activity manually. Worker startup converts the existing
`vision/activities.json` catalog into canonical shared Activity models, matching
the manual demo pipeline. Restart after catalog edits. Unknown IDs are skipped/logged.
Person-ID dashboard provisioning/read-policy gaps remain in `notes/vision-data.md`.
The deployed migration 004 requires authentication but uses demo-only authorization.
Owner-only authorization is implemented by migration 006 and awaits deployment.
Dev permits a static phone override for testing. Demo forces dynamic mode and
requires deployed migration 006 plus a teacher profile and owned session before
Photon delivery can work. This startup procedure does not deploy migrations.

## Endpoints and readiness

- Dashboard: http://localhost:3000
- Vision health: http://127.0.0.1:8000/health
- Local video: http://127.0.0.1:8000/stream (keep local)

A healthy vision demo reports an open camera and zero startup errors at /health.
The launcher surfaces component errors and stops when a required process exits;
it does not wait indefinitely for camera health.

Before demo: connect camera, check Supabase connectivity/current session/activity,
verify dashboard availability and test backend review resolution with teacher authentication, verify Groq key and
Spectrum target activation, and check person-ID visibility.
Camera-free development: `CUES_CAMERA=fake ./scripts/dev.sh`.

## Troubleshooting

- Missing `tracking_valid`: apply migration 005 to the correct project.
- `Target not allowed for this project`: activate teacher destination in Spectrum Users.
- Missing Supabase configuration: set root backend variables; public keys are insufficient.
- Camera unavailable: check OS permissions/index or use fake mode.
- Port collision: stop the process using 3000/8000, then restart.
- Photon env missing: save `cues/.env`, check required names and install nested dependencies.
- Unknown activity: align catalog with vision and restart worker.
