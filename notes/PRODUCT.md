# Cues product context

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Special-education teachers monitoring task progress at a station.
Product authority remains `notes/PRD-cues.md`; this file provides concise design context.

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

The landing page, sign-in pages and teacher workspace share one visual system:
upright Inter, EB Garamond for page titles only, big plain numbers, small spaced
captions, pill buttons and round icon buttons, in Night (landing navy) and light
(sign-in canvas) themes. The workspace looks like the dashboard the landing demo
shows. Screens stay simple and uncluttered; model and technical detail waits
behind a disclosure. Color supports explicit status text and never implies a
learner's state.

Sign-in asks one question at a time beneath the illustrated Cues companion. The
companion belongs to the product, never to a teacher or learner. `notes/DESIGN.md`
records the implemented tokens and layout.

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

The dashboard subscribes to teacher_reviews, lists pending reviews first in its
Class list, and records Support needed / No support needed through the
resolve_teacher_review RPC (behind web.teacher_review_actions). The agent's
rationale and evidence types appear behind "Why did Cues ask?". There is no
local-only decision path.

Further gaps include teacher login/profile, dynamic teacher phone lookup,
teacher/session ownership authorization, person-ID dashboard/read-policy alignment,
and activity catalog alignment. Current resolution authorization is demo-only for
authenticated users and simulated-seat reviews. Prompt history has no production
observation producer; available progress history is process-local.

## Evidence on Hand

`notes/PRD-cues.md`, `shared/contracts.py`, synthetic fixtures, and implementation notes under `notes/`.
Historical team coordination material is archived under `notes/archive/`.

Use simulated data only. Do not assume a fixed seat count unless the current
vision/dashboard provisioning contract guarantees one.

## Product Principles

- Prioritize a teacher's quick scan of task and status.
- Separate connection health from student task state.
- Preserve human decisions and the local perception boundary.
