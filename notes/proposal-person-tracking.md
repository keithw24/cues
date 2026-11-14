# Proposal: detect people, not fixed seats

Status: **draft for Evan and Michelle to review** (from Keith). Nothing in
`shared/`, `supabase/` or `agent/` has been changed.

## Summary

Today vision splits the camera frame down the middle into two fixed seats,
`S1-L` (left) and `S1-R` (right). This proposal replaces that split with
**person tracking**: vision finds each person in the frame, draws a box around
them, and reports per person. One camera can then follow 1-4 children, and they
do not have to stay on one side of a line.

Everything vision measures per child stays the same (gesture match score,
raise-hand, expression context, status, events). Only the way the frame is
divided into children changes.

The fixed-seat mode stays as a fallback (`CUES_GROUPING=seats`).

## What changes in the shared contract

The **shape** of every contract stays the same: `seat_id` is already free text
in `shared/contracts.py` and in every Supabase table. What changes is the
**meaning and lifetime** of the id.

| | Today | Proposed |
|---|---|---|
| Id format | `S1-L`, `S1-R` | `S1-P1`, `S1-P2`, ... `S1-P4` |
| What it identifies | A fixed half of the frame | One tracked person (a box that follows them) |
| How many | Always 2 | 0-4, changes as people enter and leave |
| Lifetime | Permanent | While the person stays in view; a person who leaves and returns may get a new id |
| Identity | Position only | Position only. No face recognition, nothing about who the child is is stored |

Rules vision will follow:

1. Ids are `<station>-P<n>`, numbered from 1, reusing the lowest free number.
2. An id is kept while the person stays in view. After 3 s out of view, vision
   sends `tracking_lost` for that id. After 10 s the id is released.
3. Event types, statuses and payloads do not change.
4. One new optional payload field on vision events: `"person_box": [x0, y0, x1, y1]`
   (normalised 0-1). It is a box only, not an image. Optional: consumers can
   ignore it.

Open question for the team: should vision send a `person_joined` /
`person_left` event? It would need a new `EventType` in `shared/contracts.py`.
Proposed answer: **no** for now; `tracking_lost` plus the first `seat_state`
row for a new id are enough.

## How it affects each role

### Evan (frontend + Supabase)

- **`seats` table.** Rows are no longer two fixed seats. Either:
  - (a) vision inserts a `seats` row the first time it sees a new id
    (`side` = null, `display_name` = "Person 1"), or
  - (b) the dashboard builds cards from `seat_state` rows directly.
  The `side` column (L/R) has no meaning for person ids; it can stay null.
- **Read policy.** `demo_state_read` only shows a `seat_state` row if a matching
  `seats` row exists with `is_simulated = true`. Real person ids would be
  hidden. This needs a decision either way (also true for today's real seats).
- **Dashboard cards** appear and disappear as people enter and leave, instead
  of a fixed two-card layout. Cards should be labelled "Person 1", "Person 2"
  (no names: there is no identity, only position).
- **Per-seat task override** (click a card, assign a task) still works, keyed by
  the person id, but an override is lost if that person's id changes.
- **Station page** can draw the person boxes if wanted (optional `person_box`).

### Michelle (rules engine + agent)

- **Rules keyed by `seat_id` still work**: misses, no-progress and cooldowns are
  counted per id exactly as now.
- **Ids can change.** If a child leaves and returns, their history starts again
  under a new id. Cooldowns and rolling-window counts reset for them. Rules
  should not assume a fixed set of two seats.
- **`support_preferences` is keyed by `seat_id`.** Preferences cannot be
  attached to a person id that only lasts while they are in view. Options:
  - (a) keep simulated preferences keyed by the *slot* (`S1-P1` always gets
    profile 1), accepting that it is a demo convenience, or
  - (b) drop per-child preferences for live people in the MVP and use a default
    profile.
  This is the biggest open question for the agent.
- **`tracking_lost`** will be more common (people leaving the frame). It is
  already excluded from failure counts.

### Keith (vision)

- Add MediaPipe Pose Landmarker (up to 4 people), a person box per pose, and a
  tracker that keeps ids stable between frames.
- Assign hands and faces to the person they belong to (pose wrists and nose).
- Raise-hand uses body points: wrist height above the shoulders, scaled by
  shoulder width, combined with MediaPipe's landmark visibility, gives a
  confidence score from 0 to 1.
- Keep `CUES_GROUPING=seats` as the fallback mode.
- Benchmark the laptop again: pose with several people is the heaviest model.

## Risks

- **Id swaps** when two children cross or overlap. The fixed seats avoided
  this; that is why the PRD chose them (decisions D1, D2). Mitigation: keep the
  seat mode as a fallback for the demo.
- **Partly visible children** (cut off at the chest, or behind someone) may be
  missed or merged. Pose needs head and shoulders in view.
- **Speed**: needs a benchmark on the demo laptop before we rely on it.

## Decisions needed

1. Evan: (a) vision inserts `seats` rows, or (b) dashboard reads `seat_state` only?
2. Evan: how should the read policy treat real (non-simulated) ids?
3. Michelle: support preferences by slot (a) or a default profile (b)?
4. All: agree the id format `S1-P1`... and the optional `person_box` field.
5. All: update PRD §17 and `shared/contracts.py` docs once agreed.
