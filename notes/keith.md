# Keith — Vision (CV / local perception)

Branch: `keith`. Folder: `vision/`. Status as of Nov 14, ~04:10 UTC.

## What vision does

Vision is one Python service on the station laptop. It reads the camera, works
out what each child is doing, and turns that into structured events for the
rest of Cues. Camera frames never leave the laptop; only numbers and labels do.
Vision does **not** decide when to alert the teacher. That is Michelle's rules
engine.

```
camera -> seat zones -> MediaPipe hands -> normalise -> gesture match -> match score
camera -> seat zones -> MediaPipe faces -> face crop -> HSEmotion -> expression context
                                             (milestone 2) -> status per seat -> events
```

## What works now (on `keith`)

| Piece | What it does | File |
|---|---|---|
| Camera | Reads the webcam; crops every frame to 640x480 (4:3) without stretching | `camera.py` |
| Pipeline + service | Runs stages on each frame; `/stream` (live video with overlays), `/health` (fps, flags) | `pipeline.py`, `app.py` |
| Seats | Left half = `S1-L`, right half = `S1-R`; ignores detections near the middle line; `POST /seats/swap`, `POST /seats/divider` | `seats.py`, `routes/seats.py` |
| Hands | MediaPipe hand points (21 per hand), assigned to a seat by wrist | `stages/s10_hands.py` |
| Faces | Largest face per seat and a padded crop. Location only, no face recognition | `stages/s20_faces.py` |
| Gestures | Hand points -> 63-number shape vector -> compared with recorded examples -> match score 0..1 | `gestures/`, `stages/s30_gestures.py` |
| Recorder | Records target / rest examples from the webcam, with a preview window | `record.py` |
| Expression | HSEmotion's 8 native probabilities per seat, averaged over 2 s. Supporting context only | `stages/s40_expression.py` |
| Tasks | `thumbs_up`, `raise_hand`, `custom_gesture_01`, each with its own thresholds | `activities.json`, `activities.py` |
| Printout | Per-seat summary once a second (below) | `watch.py` |
| Event emitter | Validates and writes `shared.contracts` `Event` / `SeatState` to local JSONL, or Supabase when the flag is on | `events.py` |
| Flags | Each feature can be switched off with `CUES_FLAG_*` | `flags.py`, `flags.json` |

Example output of `uv run python -m vision.watch --all-on`:

```
Seat: S1-L
Task: thumbs_up
Match score: 0.81
Expression:
  neutral: 0.61
  happiness: 0.21
  sadness: 0.04
```

## Feature flags (all off by default)

`vision.hands`, `vision.faces`, `vision.gestures`, `vision.expression`,
`vision.supabase_events`. Turn on with e.g. `CUES_FLAG_VISION_HANDS=1` in `.env`.
`vision.watch --all-on` turns on the four perception flags for that run.

## What the rest of the team can rely on

- **Events** match `shared/contracts.py` exactly (Michelle wired `vision/events.py`
  to the shared models). Types vision will emit: `attempt_success`,
  `attempt_miss`, `review_needed`, `no_progress`, `tracking_lost`,
  `expression_context` (always `supporting_only: true`, with `duration_seconds`).
- **Seat ids** are `S1-L` and `S1-R` (station from `CUES_STATION_ID`).
- **Expression** is never sent as a "struggling" signal by itself.
- **Nothing visual leaves the laptop**: no frames, crops or landmark dumps go to
  Supabase. Gesture examples stay in `vision/templates/` (git-ignored).

## Not done yet (milestone 2)

- Raise-hand rule (wrist above that seat's face).
- Per-seat status logic: idle -> in_progress -> done / review / needs_help /
  tracking_lost, using each task's thresholds and `no_progress_seconds`.
- Emitting those as events (printed as `EVENT ...` first, then via the emitter
  to Supabase). This is integration step 1: CV -> Supabase.
- Reading the current task from the app (`sessions` / overrides in Supabase)
  instead of `CUES_TASK`.
- A `POST /templates/record` endpoint for Evan's gesture-recording UI
  (recording is a command-line tool for now).

## Open issues / to verify on hardware

- Live thumbs-up scores after the framing + calibration fix need checking on
  the real camera (re-record examples first; old ones were made before the fix).
- The service ignores hands near the middle line, which is right for two
  children but awkward for one person testing. A one-seat mode may be needed.
- Calibration (`SCALE`, `REST_CAP` in `gestures/matcher.py`) may need tuning
  with real hands.

## How to run (from the repo root, in Terminal for camera access)

```bash
uv run python -m vision.record thumbs_up target --takes 3   # record examples
uv run python -m vision.record thumbs_up rest --takes 2
uv run python -m vision.watch --all-on --debug              # per-seat printout
uv run uvicorn vision.app:app                               # then open localhost:8000/stream
uv run pytest vision                                        # tests (hardware tests skipped)
```

## Update (~04:10 UTC): people mode and integration pieces

- **People mode is the default** (`CUES_GROUPING=people`): up to 4 people are
  boxed and tracked as `S1-P1`... Fixed seats remain with `CUES_GROUPING=seats`.
  See `notes/proposal-person-tracking.md` (needs Evan's and Michelle's review).
- **Status + events are built**: `attempt_success`, `attempt_miss`,
  `review_needed`, `no_progress`, `tracking_lost`, `expression_context` per
  person (flag `vision.task_status`).
- **Current task from the app**: with flag `vision.activity_sync`, vision reads
  `sessions.current_activity_id` for `CUES_SESSION_ID` once a second.
- **Recording endpoint** (flag `vision.gestures`): `POST /templates/record`
  `{activity_id, label: "target"|"rest", seconds, seat_id}`, plus
  `GET` / `DELETE /templates/{activity_id}`. Records from the running service.

## Needs from Evan

- **Resolved November 14:** migration 005 added nullable
  `seat_state.tracking_valid` to hosted Supabase. Vision's complete upsert now
  succeeds without filtering the shared contract. A live publisher-path check
  persisted `true` for a valid observation and `false` with null `task_score`
  for tracking loss.
- **Supabase keys** for the station laptop (`SUPABASE_URL`,
  `SUPABASE_SERVICE_ROLE_KEY` in the root `.env`) and a `sessions` row id for
  `CUES_SESSION_ID`, so the CV -> Supabase step can be tested for real.

## Update: people only, new overlay

- **Seats mode is removed.** Vision only reports people (`S1-P1`...). The
  dashboard must handle person ids (see `notes/proposal-person-tracking.md`).
- **Overlay:** per person, a face box labelled `P1  neutral 0.61`, one hand
  (skeleton + box labelled with the task score, coloured green / orange / grey
  against the task thresholds) and a line from the hand to the face. No face
  visible: only the hand box, labelled `P1  ...`. `--debug` shows every stage's
  detail instead.
- **One hand per person:** the best-matching hand for gestures, the highest
  hand for raise-hand.

## Update: Logitech C930e, 16:9

- Station camera is the Logitech C930e. Frames are processed at 960x540
  (16:9, full wide view, no cropping); the camera is asked for 1280x720.
- Set `CUES_CAMERA_INDEX=1` in `.env` if the Mac's built-in camera is 0.
- Geometry is aspect-corrected; recorded custom gestures (format 4) must be
  re-recorded. Thumbs-up is built in (Gesture Recognizer) and needs nothing.
