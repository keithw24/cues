# Local startup

Use Python 3.11 with uv, Node 22+ and npm, a Logitech camera with OS camera
permission, and configured hosted Supabase/Spectrum projects.

```bash
uv sync
npm --prefix web ci
npm --prefix cues ci
./scripts/dev.sh
```

The launcher starts vision on port 8000, `agent.worker`, and Next.js on port 3000.
Component logs are prefixed. Ctrl-C/SIGTERM stops process groups, with forced
termination after a five-second grace period per child. A component exit stops
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

For live publication enable `CUES_FLAG_VISION_SUPABASE_EVENTS`,
`CUES_FLAG_VISION_TASK_STATUS`, `CUES_FLAG_VISION_ACTIVITY_SYNC`,
`CUES_FLAG_VISION_HANDS`, `CUES_FLAG_VISION_FACES`, `CUES_FLAG_VISION_GESTURES`,
`CUES_FLAG_VISION_RAISE_HAND`, and `CUES_FLAG_VISION_EXPRESSION` with value `1`.
Weights may download on first use. Fake frames do not simulate student progress.

`web/.env.local`: browser-safe `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`; enable `CUES_FLAG_WEB_DASHBOARD=1`.
Consult `web/README.md` for available teacher review UI flags/authentication.
Never expose service-role, Groq, or Spectrum credentials as `NEXT_PUBLIC_*`.

`cues/.env`: backend-only `SPECTRUM_PROJECT_ID`, `SPECTRUM_PROJECT_SECRET`,
`SPECTRUM_TEACHER_PHONE`; optional `SPECTRUM_SENDER_PHONE` selects the sending
line. The teacher number is the fixed demo/test destination; dynamic profile
lookup is future work. Add the opted-in destination to active Spectrum Users.
The sender loads this file relative to its module, independent of working directory.

## Database and demo prerequisites

Apply migrations 001 through 005 in filename order; see `supabase/README.md`.
The current hosted project already has `seat_state.tracking_valid`,
`teacher_reviews`, authenticated `resolve_teacher_review` RPC, and Realtime
publication membership. Do not reapply initial schema to that project.

Provision the session and activity manually. Worker startup reads the Supabase
`activities` catalog using canonical Activity fields; restart after catalog edits.
Align it with `vision/activities.json`. Unknown activity IDs are skipped/logged.
Person-ID dashboard provisioning/read-policy gaps remain in `notes/vision-data.md`.
Teacher review resolution requires authentication; current demo authorization
does not implement classroom ownership.

## Endpoints and readiness

- Dashboard: http://localhost:3000
- Vision health: http://127.0.0.1:8000/health
- Local video: http://127.0.0.1:8000/stream (keep local)

Before demo: connect camera, check Supabase connectivity/current session/activity,
enable dashboard/review controls with teacher authentication, verify Groq key and
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
