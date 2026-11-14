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

Cues is the product name. The user delegated visual judgment for this first
dashboard and requested the Impeccable skill. No existing school style is supplied.

## Evidence on Hand

`PRD-cues.md`, `TEAM_WORKFLOW.md`, `shared/contracts.py` and synthetic fixtures.
Supabase has two simulated seat rows. No real student data or imagery is used.

## Product Principles

- Prioritize a teacher's quick scan of task and status.
- Separate connection health from student task state.
- Preserve human decisions and the local perception boundary.
