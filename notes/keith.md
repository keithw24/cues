# Keith — Vision (CV / local perception)

Branch: `keith`. Folder: `vision/`. Status as of Nov 14, ~03:10 UTC.

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
