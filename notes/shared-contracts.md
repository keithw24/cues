# Shared contracts

`contracts.py` is the canonical Python definition of exchanged Cues data.
Import models from `shared.contracts`; do not define component-specific copies.
Models have no camera, network, routing, or service dependencies beyond Pydantic.

```python
import json
from pathlib import Path

from shared.contracts import Event

rows = json.loads(Path("shared/fixtures/events.json").read_text())
events = [Event.model_validate(row) for row in rows]
wire_data = events[0].model_dump(mode="json")
schema = Event.model_json_schema()
```

Run from the repository root. JSON fixtures use fixed UUIDs/timestamps and only
synthetic data. Each file is an array of its corresponding model:

- `activities.json`: rule-based raise hand and a calibrated static gesture.
- `events.json`: all 12 event types, including three consecutive misses and a
  sustained expression event. These are input examples, not a routing policy or
  a causal end-to-end session; expression alone never establishes task struggle.
- `seat_states.json`: alternative snapshots covering all six seat statuses.
- `alerts.json`: alternative pending, approved, and dismissed examples.

Session/alert IDs are UUIDs; other IDs are strings. Timestamps require a timezone.
Scores are match scores, not probabilities; expression probabilities retain
their native meaning. Live expression context may omit duration; sustained
expression events require it. `SeatState` is a full snapshot, not a patch.
`payload` and `evidence` accept JSON metadata; producers remain responsible for
excluding images, recordings, secrets, and unnecessary personal information.

Activity keywords/configuration and detailed non-expression event payloads are
deferred until their consumers need an agreed shape. Generate app types from
the models' JSON Schema when needed; avoid independently authored definitions.

The vision emitter imports these models directly. `emit(event)` accepts a complete
`Event`; `update_seat_state(state)` accepts a complete `SeatState`. Both validate
before queuing JSON data, including explicit nulls to clear stale seat values.
Construct models with the producer's session/station IDs and aware timestamps;
the emitter exposes `session_id` (a UUID) and `station_id` as producer defaults.
It never injects IDs into or mutates a supplied model. Its existing background
writes, feature flag, and local fallback are preserved.

Checks from the root:

```bash
uv run pytest shared/tests
uv run ruff check shared
uv run ruff format --check shared
```

## Teacher-managed session context

`Session` is the immutable station lifecycle projection: UUID `id`, string
`station_id`, nullable `current_activity_id`, aware `started_at`/nullable
`ended_at`, and nonnegative integer `revision`. Vision selects only those fields
from Supabase. `SeatState.session_revision` is optional for legacy producers;
managed observations require the exact saved revision. Perception events carry it
in `payload.session_revision`. No new task/review/event states were introduced.

Session changes increment revision; a new session has a new UUID. The vision
consumer pins the context per frame, resets its trackers on UUID/revision change,
and pauses after end or sync loss. The database rejects stale/ended managed
observations. Future live progress/routing consumers must use the same lifecycle
to call their existing reset hooks on restarts; ProgressEvaluator itself is
unchanged. See `notes/web-session-controls.md` and `notes/session-lifecycle.md` for
transport, flags, rollout status and outstanding hardware verification.
