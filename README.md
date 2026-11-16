# Cues

Cues helps a special-education teacher see which students may need attention. A camera on the
teacher's laptop watches simple tasks (raise a hand, thumbs up, a gesture the teacher recorded).
A rules engine decides when a stall matters, an AI agent writes a short review request, and the
teacher decides every outcome. Student video never leaves the laptop.

Rules for working in the repo are in [CLAUDE.md](CLAUDE.md). Everything else is below.

## How it works

```mermaid
flowchart TD
    T["Teacher signs in"] --> ST["Own default station"]
    ST --> CF["Dashboard tells local vision its station (POST /config)"]
    A["Teacher picks an activity"] --> SS["sessions row"]
    C["Camera"] --> V["Vision: MediaPipe + HSEmotion (on the laptop)"]
    CF --> V
    SS --> V
    V -->|"seat_state + events, ~every 1s per person"| DB[("Supabase")]
    DB --> W["Agent worker: ProgressEvaluator, escalation, router"]
    W --> K["Deep Agent (Groq) -> request_teacher_review"]
    K --> R["teacher_reviews"]
    W -->|"evaluated progress"| DB
    R --> D["Dashboard"]
    R --> P["Photon / Spectrum text message"]
    D --> X{"Teacher"}
    P --> X
    X -->|"Support needed / No support needed"| RR["resolve_teacher_review"]
    X -->|"Mark as reviewed"| MR["mark_seat_reviewed: child back to Working"]
```

- **Vision** (`vision/`, FastAPI on :8000) reads the camera, tracks people by position only, scores
  the current task and publishes structured status. `/stream` (MJPEG) is the local video, read
  directly by the browser.
- **Agent worker** (`agent/`) polls `seat_state` for the station's active session, tracks progress,
  and asks the LLM only when a stall is long enough. Groq `openai/gpt-oss-20b` is the demo model;
  the core is provider-independent. It never sees frames and only creates review requests.
- **Dashboard** (`web/`, Next.js on :3000) is where a teacher signs in, starts a session, sees who
  is in view, and answers review requests.
- **Database** (`supabase/`) holds ordered migrations. Run it locally with Docker.
- **Notifications** (`cues/`) is a nested Photon/Spectrum SDK project, run on demand to send the
  teacher an iMessage.
- **Contracts** (`shared/contracts.py`) are the authoritative data shapes for events, seat state,
  sessions and reviews.

## Run it

You need Python 3.11 with [uv](https://docs.astral.sh/uv/), Node 22, Docker and the
[Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started).

```bash
uv sync
npm --prefix web ci          # also installs cues/
supabase start               # local Postgres + Auth + Realtime; applies every migration
supabase status              # prints the URL and keys for the next step
```

Put these in the root `.env` (backend only, never commit it; `.env.example` lists the rest):

```
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_SERVICE_ROLE_KEY=<secret key from supabase status>
GROQ_API_KEY=<your key>
```

and these in `web/.env.local` (browser-safe):

```
NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<publishable key from supabase status>
```

Then:

```bash
./scripts/dev.sh             # vision + agent worker + dashboard, normal timings
./scripts/demo.sh            # same, with short timings for presenting
CUES_CAMERA=fake ./scripts/dev.sh   # no webcam
```

Open http://localhost:3000, sign up (confirmation mail appears at http://127.0.0.1:54324),
start a session, and allow camera access for your terminal in System Settings. The launcher
stops its own leftovers on start and shuts everything down on Ctrl-C. `supabase db reset` wipes
the local database; `supabase stop` shuts it down.

**Useful settings** (root `.env` or the shell):

| Variable | Use |
|---|---|
| `CUES_CAMERA_INDEX` | Webcam number (default 0; a USB camera is often 1) |
| `CUES_CAMERA` | `fake` for camera-free startup |
| `CUES_FLAG_<AREA>_<NAME>` | Override a feature flag from `flags.json` with `1` or `0` |
| `CUES_USE_STATIC_TEACHER_PHONE` | `1` sends alerts to `SPECTRUM_TEACHER_PHONE` (testing); `0` looks up the session owner's saved phone (`demo.sh` forces 0) |
| `CUES_OVERLAY` | `debug` draws every stage's detail on the video |
| `CUES_PALM_FLIP` | `1` if a camera mirrors its output |
| `CUES_STATION_ID` / `CUES_SESSION_ID` | Dev/test overrides only; normally the dashboard sends the station |

Text messages need `SPECTRUM_PROJECT_ID` and `SPECTRUM_PROJECT_SECRET` in `cues/.env`, the
teacher to opt in under Settings > Profile, and the number added to Users on the Spectrum
website.

## Tests

There are no unit tests. Two suites check that the parts work together; both need `supabase start`:

```bash
uv run pytest tests/contract   # code, Python contracts, TypeScript parsers and the schema agree
uv run pytest tests/smoke -s   # vision follows a session, a stalled child becomes a review,
                               # the dashboard reads it, Mark as reviewed closes it
```

CI (`.github/workflows/ci.yml`) starts a local Supabase and runs both; a skipped test fails it.
Web checks: `cd web && npx tsc --noEmit && npm run lint && npm run build`.

## Feature flags

Every feature has a flag in `flags.json`, default off unless noted there. `CUES_FLAG_VISION_HANDS=0`
turns hand tracking off; the dashboard reads `NEXT_PUBLIC_CUES_FLAG_...` for flags the browser needs.
Each area reads flags only through its helper (`vision/flags.py`, `web/lib/flags.ts`); an unknown
name is an error. `/health` on vision lists its current flags.

## Troubleshooting

- **Camera unavailable:** allow camera access for the terminal app, check `CUES_CAMERA_INDEX`, or use fake mode.
- **"Station is in use by another camera":** a second camera or laptop holds the station; close it or sign in with its own account.
- **Port in use:** the launcher frees 3000 and 8000 when it can verify they are this repo's.
- **Supabase ports taken:** another local Supabase project is running; `supabase stop --project-id <name>`.
- **Dashboard still shows "Needs Review" after Mark as reviewed:** vision must be running with `vision.review_marks` on (the default).
- **Missing Supabase configuration:** the backend needs the secret key in the root `.env`; public keys are not enough.

## Status

**Working** (checked by the contract and smoke tests): teacher sign-in and default station; session
start/end and activity picker; one camera per station; person tracking by position; built-in gestures
and teacher-recorded gestures on the laptop; raise-hand; stall detection and agent review requests;
persistent reviews with Support needed / No support needed and Mark as reviewed; live evaluated
progress; Photon text on a new review; local Docker Supabase.

**Open work**

| Item | Notes |
|---|---|
| Real-camera pass | Pointing, peace, fist; Mark as reviewed (timer restarts, new review only after a fresh stall); id stability; two laptops on two stations; the camera health strip and "waiting for review" list. Only the automated suites have run them. |
| Write volume | Vision rewrites each person's `seat_state` row every second (about 3,600 writes an hour per person, plus lease and session reports). A 3-second heartbeat works only if the agent's observation-gap limit rises from 3s to 5s; a throttle for the dashboard's refreshes and station reports was also prototyped. Not applied. |
| Rotate exposed keys | A Groq key and a Cursor key were shown in logs earlier in the build. |
| "Add a gesture" screen | The vision API (`/gestures`, `/templates/record`) exists; there is no dashboard screen, and a recorded gesture is not registered in `activities`. |
| Interventions | Menu, suggestion and approval exist behind `agent.interventions` / `web.interventions` (off). Applying an approved support to a task is not built. |
| Database one-writer rule | The one-camera guard is enforced in vision only; add a `writer_id` check to `seat_state` writes. |
| Review evidence | While a review is open, later evaluations are dropped, so the teacher never sees newer evidence. |
| History | Progress and prompt history are in memory and lost on restart. |
| Person ids | By position only, so a person who leaves for 10+ seconds or two who swap seats can change ids. |
| Refactor leftovers | The dashboard header and hero controls are still inline in `web/components/dashboard.tsx`. |

**Ideas:** end-of-session summary; gesture tuning screen; per-session reports; moving gestures,
object-state tasks, voice (all optional); more than one camera per classroom (decided not now).

**Known limits:** one agent worker per station; Photon acceptance is not proof of handset delivery;
the model call can delay polling and cause a conservative gap reset; `/stream` MJPEG is the
intentional local transport.

## Layout

| Path | Contents |
|---|---|
| `vision/` | Camera, perception stages, task status, local API and video |
| `agent/` | Progress evaluation, routing, Deep Agent, review store, notifications, launcher |
| `web/` | Dashboard, sign-in, settings, landing page |
| `shared/` | Python contracts and fixtures |
| `supabase/` | Migrations and seed |
| `cues/` | Spectrum SDK sender (nested project) |
| `tests/` | Contract and smoke tests |
| `scripts/` | `dev.sh`, `demo.sh`, cleanup tools |
