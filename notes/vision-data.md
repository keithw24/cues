# Vision data handoff

Canonical exchanged fields are defined in `shared/contracts.py`; SQL migrations
under `supabase/migrations/` define persistence. See [Keith's notes](keith.md)
for perception and [Michelle's notes](michelle.md) for consumption.

## Primary feed: seat_state

Vision upserts one latest row per seat_id, on status/tracking changes and otherwise
about once per second. Fields: seat_id, session_id, activity_id, status,
updated_at, tracking_valid, task_score, expression_context.
updated_at is the observation time, not the network send time.

tracking_valid is nullable: true is a valid current observation, false is missing
tracking, null is unknown historical state. Invalid tracking publishes null
task_score; it never counts as student failure. Migration 005 added the nullable
boolean without a default and was verified through live publisher upserts.

Expression is supporting-only. Qualifying sustained context includes label,
probability and duration_seconds; otherwise it is null. No frames or images go
to Supabase or the LLM.

## Consumers and task selection

The continuous worker polls seat_state and runs ProgressEvaluator → progress
history recording → EscalationEvaluator → EvaluationRouter → ContextEnricher
→ Deep Agent → persistent teacher_reviews. New persisted reviews can notify through
Photon/Spectrum; teacher resolution uses the authenticated Supabase RPC.

Vision reads sessions.current_activity_id for CUES_SESSION_ID once per second
when activity_sync is enabled. The dashboard's current activity controls and
persistent review UI still require integration in this checkout. Backend review
resolution exists; observation-local hiding is not its replacement.

Vision reports temporary person IDs such as S1-P1. Person-ID provisioning/read
policies and alignment between vision's activity catalog and Supabase activities
remain gaps. Do not assume fixed seat counts or persistent student identity.

## Other outputs and local video

Events are informational audit/debug observations, not the primary routing feed.
The background emitter falls back to local event JSONL and latest-state JSON
when cloud publication is unavailable. Gesture templates stay local.
MJPEG /stream is the intentional local demo transport; WebRTC is not required.

Setup and env details: [STARTUP](../STARTUP.md). Product authority:
[PRD](../PRD-cues.md). Use simulated data only.

## Teacher-recorded gestures (dashboard API, for Evan)

Vision exposes a local HTTP API so the dashboard can let a teacher add a new
gesture by recording it. No UI is built yet; this section is the contract.

Turn it on in the root `.env`: `CUES_FLAG_VISION_CUSTOM_GESTURES=1` (the
`/templates` recording routes are on whenever `vision.gestures` is on, which
`./scripts/dev.sh` already enables). Base URL: `http://127.0.0.1:8000`. The
browser may call it directly from `http://localhost:3000` (CORS); other origins
can be allowed with `CUES_DASHBOARD_ORIGINS` (comma-separated).

| Call | Body | Returns |
|---|---|---|
| `GET /gestures` | | list of gesture objects (below) |
| `POST /gestures` | `{"name": "Wave", "keywords": ["wave"]}` (keywords optional) | 201, the new gesture; 422 if the name has no letters/digits |
| `POST /templates/record` | `{"activity_id": "custom_wave", "label": "target" or "rest", "seconds": 2, "seat_id": "S1-P1"}` (`seconds` 0-10, default 2; `seat_id` optional, default the largest hand in view) | `{"captured": 18, "activity_id", "target_examples", "rest_examples", "rejection_threshold"}`; 422 if no hand was seen |
| `GET /templates/{id}` | | the same counts |
| `DELETE /templates/{id}` | | clears that gesture's examples (re-record) |
| `DELETE /gestures/{id}` | | removes a dashboard-created gesture and its examples; 404 for catalog gestures |

Gesture object:

```json
{"id": "custom_wave", "name": "Wave", "builtin": false, "custom": true,
 "success_threshold": 0.78, "review_threshold": 0.58,
 "target_examples": 18, "rest_examples": 12, "ready": true}
```

Built-in gestures (thumbs_up, open_palm, pointing, peace, fist) have
`builtin: true`, `ready: true` and null example counts; they cannot be recorded.

Suggested teacher flow:
1. Teacher types a name -> `POST /gestures`; keep the returned `id`.
2. "Show the gesture": show a 3-2-1 countdown in the UI, then
   `POST /templates/record` with `label: "target"`. The request blocks for
   `seconds` while vision samples the live camera. Do this 3 times, asking for
   a slightly different angle each time. Show `captured`; if 422, ask the
   teacher to keep the whole hand in view.
3. "Relax your hand / show other gestures": 2 takes with `label: "rest"`.
4. `ready` is true: the gesture is detected live immediately (green on the
   video, and in `seat_state` / events when it is the current task).

Notes:
- Recording uses the running service and camera; nothing needs restarting.
  `agent.worker` reads the catalog at start, so restart the stack before
  assigning a new gesture as the current task.
- The id must also exist in the Supabase `activities` table before
  `sessions.current_activity_id` can point at it (insert `id`, `name`,
  `check_type: "gesture"`, thresholds from the gesture object).
- Privacy: only the gesture name goes to Supabase. The definition and the hand
  examples stay in `vision/templates/` on the laptop (git-ignored). The API
  never returns images or landmarks.
