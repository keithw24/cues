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
