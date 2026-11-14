# Cues product context

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Special-education teachers monitoring task progress at a station.
Product authority remains `PRD-cues.md`; this file provides concise design context.

## Product Purpose

Make structured task state visible so a teacher can decide who needs support.
The dashboard loads structured station state and updates without a refresh.
The implemented backend routes meaningful stalled progress into persistent
teacher reviews, with the teacher retaining the final attention decision.

## Operating Context

Next.js and Tailwind frontend; Supabase structured state and realtime delivery.
Perception stays local. A continuous Python worker consumes Supabase SeatState:
ProgressEvaluator → progress history recording → EscalationEvaluator → EvaluationRouter → ContextEnricher
→ Deep Agent → teacher_reviews. FastAPI serves local vision/video.
The backend supports teacher review resolution; frontend integration in this
checkout still has the gaps listed below.

## Capabilities and Constraints

- All hackathon seat data is simulated and labeled SIM.
- Use shared status names from `shared/contracts.py`.
- SeatState includes nullable tracking_valid. Tracking loss is missing observation,
  never student failure; invalid tracking carries a null task score.
- Camera data and local gesture templates never enter cloud services.
- Teacher review choices are Needs attention and Dismiss. They record attention
  decisions, without automatically selecting support or changing instruction.
- Expression model output never independently establishes task difficulty.
- The dashboard must show loading, empty, error and disconnected states honestly.

## Brand Commitments

The latest user-pinned brief supersedes all earlier screenshot directions. Cues
should resemble restrained operational software: a neutral canvas, white surfaces,
Courier Prime, thin borders, compact spacing, small corners and quiet normal statuses.
Local video dominates beside an attention queue; only Needs Review receives strong
status emphasis. The latest admin screenshots refine the palette to white/navy,
cool gray, teal selection/live text and coral review, with no status dots or label
icons. The user subsequently requested Courier Prime typewriter typography; the operational layout remains. The provided Card primitive is
integrated without a shadow; no hero/beam implementation was supplied. No gradient,
glass, hero, giant rounded cards or main-screen charts.

## Current Implementation Limits

The existing Supabase snapshot/realtime flow remains in place. MJPEG is the
intentional local demo transport; WebRTC is not required. Video is an opt-in browser connection directly to the
station service at `http://127.0.0.1:8000/stream` (MJPEG), restricted by the adapter
to a localhost dashboard. There is no cloud video proxy.

Pending agent reviews are stored in Supabase teacher_reviews, including trusted
identity/priority, rationale, evidence_used and progress/escalation context in
evaluation. resolve_teacher_review(review_id, action) persists pending → confirmed
(Needs attention) or dismissed (Dismiss), with resolution time. Resolved reviews
cannot be resolved again. These backend capabilities are implemented.

Photon 2.0/Spectrum iMessage notification is implemented and acknowledgement-tested.
A new persisted pending review triggers a minimal message directing the teacher
back to Cues; duplicates and resolution do not notify. Notification failure leaves
the review available. No images, expression labels or detailed rationale go to messaging.

Current frontend gap: seat selection opens details, but this checkout's dashboard
still uses observation-local hiding and placeholder progress/assessment panels.
That local dismissal is obsolete as the product review-resolution model; frontend
agents should connect the persistent review actions rather than treating local
hiding as teacher resolution. teacher_reviews subscription, RPC action wiring,
and display of the available rationale/evidence/progress context remain to be
connected in this frontend. End session is disabled.

Further gaps include teacher login/profile, dynamic teacher phone lookup,
teacher/session ownership authorization, person-ID dashboard/read-policy alignment,
and activity catalog alignment. Current resolution authorization is demo-only for
authenticated users and simulated-seat reviews. Prompt history has no production
observation producer; available progress history is process-local.

## Evidence on Hand

`PRD-cues.md`, `shared/contracts.py`, synthetic fixtures, and implementation notes under `notes/`.
Historical team coordination material is archived under `notes/archive/`.

Use simulated data only. Do not assume a fixed seat count unless the current
vision/dashboard provisioning contract guarantees one.

## Product Principles

- Prioritize a teacher's quick scan of task and status.
- Separate connection health from student task state.
- Preserve human decisions and the local perception boundary.
