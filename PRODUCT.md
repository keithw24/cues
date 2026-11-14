# Cues product context

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Special-education teachers monitoring task progress at a station. Students use a
separate simple station interface. Product authority remains `PRD-cues.md`.

## Product Purpose

Make structured task state visible so a teacher can decide who needs support.
The initial dashboard loads simulated seats and updates without a refresh.

## Operating Context

Next.js and Tailwind frontend; Supabase structured state and realtime delivery.
Perception stays local. Current implementation scope is a read-only dashboard.

## Capabilities and Constraints

- All hackathon seat data is simulated and labeled SIM.
- Use shared status names from `shared/contracts.py`.
- Tracking loss is missing observation, never student failure.
- Camera data and local gesture templates never enter cloud services.
- Teacher approval precedes task or support changes; this slice has no write controls.
- Expression model output never independently establishes task difficulty.
- The dashboard must show loading, empty, error and disconnected states honestly.

## Brand Commitments

The approved Columbia Catalog / LionPlan direction supersedes the earlier Courier
Prime, Nexus mesh-tile and italic type treatments. Cues is quiet operational
software: upright Inter, white content, cool neutral framing, navy actions and
selection, thin borders and compact rounded controls. A persistent workspace rail
becomes compact header navigation on mobile. Camera and teacher review context
lead; activity management opens progressively and people use scan-friendly rows.
Color supports explicit status text rather than implying learner state.

Login asks one question at a time beneath an animated illustrated Cues companion.
The character belongs to the product, never to a teacher profile or learner
identity. It follows the pointer with a restrained gaze, sleeps during password
entry and honors reduced motion. The login feature defaults off with an honest
unavailable fallback. This is a code-led reference adaptation, not a pixel-exact
copy. `DESIGN.md` records the implemented tokens and component rules;
`.impeccable/teacher-workspace.md` records the approved direction.

## Current Implementation Limits

The existing Supabase snapshot/realtime flow remains in place. No WebRTC component
exists in this repository. Video is an opt-in browser connection directly to the
station service at `http://127.0.0.1:8000/stream` (MJPEG), restricted by the adapter
to a localhost dashboard. There is no cloud video proxy.

Seat selection opens a detail panel. Dismiss hides one observation key for this
visit, without changing seat state; new observations can reappear and dismissed
items can be restored. End session is disabled. Progress history and agent
assessment are explicitly unavailable. These controls do not apply interventions.

## Evidence on Hand

`PRD-cues.md`, `TEAM_WORKFLOW.md`, `shared/contracts.py` and synthetic fixtures.
Supabase has two simulated seat rows. No real student data or imagery is used.

## Product Principles

- Prioritize a teacher's quick scan of task and status.
- Separate connection health from student task state.
- Preserve human decisions and the local perception boundary.
