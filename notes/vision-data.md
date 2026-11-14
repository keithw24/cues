# Vision data: exactly what vision sends and reads

Owner: Keith. This describes the data the vision service exchanges with
Supabase, and how Evan's dashboard and Michelle's agent use it. Shapes are the
models in `shared/contracts.py`; every row is validated against them before it
is sent. The examples below were produced by the real code path (status stage
-> shared contracts), not written by hand.

## Flow

```text
camera (station laptop)
  -> vision: people, hands, faces, gesture / raise-hand score, expression
  -> status per person (vision/status.py)
       |-- Event      --insert-->  Supabase `events`      --> Michelle: rules engine
       '-- SeatState  --upsert-->  Supabase `seat_state`  --> Evan: dashboard cards
                                                          --> Michelle: progress evaluator
Supabase `sessions.current_activity_id`  --read every 1 s-->  vision (current task)

video: vision /stream (127.0.0.1:8000) --> dashboard "Live classroom" panel,
       on the station laptop only. Never sent to Supabase or any cloud service.
```

Vision writes only when `vision.supabase_events` is on and the keys are set;
otherwise the same rows go to `vision/logs/*.jsonl`. Vision reads the task only
when `vision.activity_sync` is on.

## Identity: `seat_id` is a person id

| Field | Value | Meaning |
|---|---|---|
| `station_id` | `S1` | The camera / laptop (`CUES_STATION_ID`) |
| `seat_id` | `S1-P1`, `S1-P2`, `S1-P3`, `S1-P4` | One tracked person, by position only (no face recognition) |
| `session_id` | UUID (`CUES_SESSION_ID`) | The `sessions` row; demo: `00000000-0000-4000-8000-000000000001` |

A person keeps their id while in view. Out of view for 3 s: `tracking_lost`.
After 10 s the id is released; a returning child may get a new id.

## 1. `Event` -> table `events` (insert)

```json
{
  "session_id": "00000000-0000-4000-8000-000000000001",
  "station_id": "S1",
  "seat_id": "S1-P1",
  "type": "attempt_success",
  "created_at": "2026-11-14T05:00:00.000000Z",
  "activity_id": "raise_hand",
  "score": 0.82,
  "payload": {"source": "auto"}
}
```

| Field | Type | Notes |
|---|---|---|
| `session_id` | UUID | |
| `station_id` | text | |
| `seat_id` | text | person id |
| `type` | text | one of the six vision types below |
| `created_at` | timestamp (UTC, ISO 8601) | when vision sent it |
| `activity_id` | text | the person's task at that moment |
| `score` | number 0-1 or null | see the table below |
| `payload` | JSON object | `{"source": "auto"}`, or the expression context |

### Event types vision sends

| `type` | When it is sent | `score` | `payload` |
|---|---|---|---|
| `attempt_success` | score >= task's success threshold for 1 s (status -> `done`) | best score in that 1 s | `{"source": "auto"}` |
| `review_needed` | score in the review band for 2 s, once per task (status -> `review`) | best score in that 2 s | `{"source": "auto"}` |
| `attempt_miss` | hand visible, score below review threshold for 1 s; one per time the hand comes into view | the low score | `{"source": "auto"}` |
| `no_progress` | no score reached the review threshold within the task's `no_progress_seconds` of visible time (status -> `needs_help`) | best score so far, or null | `{"source": "auto"}` |
| `tracking_lost` | no hand and no face for 3 s (status -> `tracking_lost`) | null | `{"source": "auto"}` |
| `expression_context` | anger, fear or sadness >= 0.5 for 5 s; once per episode; never changes status | null | expression context (below) |

`expression_context` example:

```json
{
  "session_id": "00000000-0000-4000-8000-000000000001",
  "station_id": "S1",
  "seat_id": "S1-P1",
  "type": "expression_context",
  "created_at": "2026-11-14T05:00:00.000000Z",
  "activity_id": "raise_hand",
  "score": null,
  "payload": {
    "label": "sadness",
    "probability": 0.63,
    "duration_seconds": 5.0,
    "supporting_only": true
  }
}
```

`label` is one of HSEmotion's 8 classes (`anger`, `contempt`, `disgust`,
`fear`, `happiness`, `neutral`, `sadness`, `surprise`); only `anger`, `fear`
and `sadness` produce this event. It is supporting model output, never a
diagnosis or a failure signal on its own.

Vision does not send `teacher_verified`, `agent_invoked`, `alert_created`,
`teacher_approved`, `teacher_dismissed` or `intervention_applied`; those
belong to the dashboard and the agent.

### What the score means

| Task type | Score | Source |
|---|---|---|
| gesture (`thumbs_up`, `custom_gesture_01`) | match score 0-1: how close the person's best hand is to the teacher's recorded examples. Not a probability. | `vision/gestures/matcher.py` |
| rule (`raise_hand`) | raise confidence 0-1: wrist height above the shoulders, in shoulder widths, times MediaPipe visibility | `vision/stages/s35_raise_hand.py` |

Thresholds are per task (`vision/activities.json`): `thumbs_up` and
`custom_gesture_01` success 0.78 / review 0.58; `raise_hand` success 0.7 /
review 0.4.

## 2. `SeatState` -> table `seat_state` (upsert on `seat_id`)

Sent on every status change, otherwise once per second per person. One row per
person; each write replaces the previous one (the live expression is not kept
as history).

The full contract object:

```json
{
  "seat_id": "S1-P1",
  "session_id": "00000000-0000-4000-8000-000000000001",
  "status": "done",
  "updated_at": "2026-11-14T05:00:00.000000Z",
  "activity_id": "raise_hand",
  "tracking_valid": true,
  "task_score": 0.82,
  "expression_context": {
    "label": "sadness",
    "probability": 0.63,
    "duration_seconds": null,
    "supporting_only": true
  }
}
```

**What actually reaches Supabase today:** the same object **without
`tracking_valid`**, because the `seat_state` table has no such column (see
"Gaps").

| Field | Type | Notes |
|---|---|---|
| `seat_id` | text | person id; primary key |
| `session_id` | UUID | |
| `status` | text | `idle`, `in_progress`, `review`, `done`, `needs_help`, `tracking_lost` |
| `updated_at` | timestamp (UTC) | |
| `activity_id` | text | the person's current task |
| `tracking_valid` | boolean | `false` only while `tracking_lost` (**not stored yet**) |
| `task_score` | number 0-1 or null | latest score for the task; null when it cannot be judged |
| `expression_context` | JSON or null | strongest current expression; `duration_seconds` is null here |

## 3. What vision reads

| Table | Field | How often | Use |
|---|---|---|---|
| `sessions` | `current_activity_id` where `id = CUES_SESSION_ID` | once per second | the class-wide task for every person |

Unknown activity ids are ignored with a warning. Vision knows `thumbs_up`,
`raise_hand` and `custom_gesture_01` (`vision/activities.json`).

## How Evan's dashboard uses it

From `web/lib/dashboard-feed.ts`, the dashboard reads `seats`, `seat_state`,
`activities` and `stations` (not `events`).

- A card is built per row of `seats`, with its live `seat_state`.
- **Gap:** `seats` has rows only for `S1-L` and `S1-R`, so person rows
  (`S1-P1`...) in `seat_state` are not shown, and the read policy hides
  `seat_state` rows without a matching simulated `seats` row.
- The dashboard sets the task in `sessions.current_activity_id`, which vision
  reads. Only `raise_hand` exists in `activities`.
- The "Live classroom" panel shows `http://127.0.0.1:8000/stream` from the
  laptop it runs on.

## How Michelle's agent uses it

- `agent/progress.py` reads `SeatState` snapshots: `status`, `task_score`,
  `activity_id` and **`tracking_valid`**. A snapshot only counts when
  `tracking_valid is True` and status is not `idle` / `tracking_lost`.
- **Gap:** snapshots read back from Supabase have no `tracking_valid` (the
  column is missing), so the progress evaluator would treat every person as
  untracked. The column is needed for Michelle's logic too.
- `agent/escalation.py` uses `expression_context` only to raise priority on
  stalled progress, matching the "supporting only" rule.
- The rules engine reads `events` per `seat_id`; with person ids, history
  restarts when a child gets a new id.

## Gaps (owned by Evan unless noted)

1. Add `tracking_valid boolean` to `seat_state`. Needed by Michelle's progress
   evaluator. Then Keith removes `SEAT_STATE_COLUMNS` in `vision/events.py`.
2. Show person ids on the dashboard: `seats` rows for `S1-P1`...`S1-P4` (or
   cards built from `seat_state`), and a read policy that allows them.
3. Add `thumbs_up` and `custom_gesture_01` to `activities`.
4. Michelle: support preferences are keyed by `seat_id`, which is now a
   short-lived person id (see `notes/proposal-person-tracking.md`).
