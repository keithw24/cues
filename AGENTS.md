# Cues — Agent Instructions

## 1. Source of truth

- Read the product/architecture source of truth, [PRD-cues.md](PRD-cues.md), before implementing product behavior. The requested `prd.md` is named `PRD-cues.md` in this repository; do not create a duplicate.
- `pyproject.toml` and `uv.lock` define the shared Python environment; `web/package.json` and `web/package-lock.json` define frontend dependencies.
- Inspect existing code before assuming paths, commands, or capabilities. Code establishes what is implemented; the PRD defines intended behavior. Surface discrepancies rather than silently rewriting architecture.
- Read `notes/archive/TEAM_WORKFLOW.md` for team branches, ownership, and shared contract decisions. It takes precedence over older branch/ownership guidance. Consult `CLAUDE.md` for feature flags and pre-merge review; follow `web/AGENTS.md` for frontend edits.
- Agreed contracts: UUID session/alert IDs; all 12 PRD event types; retain `SeatState.session_id`/`updated_at` and `Alert.created_at`/`resolved_at`; expression `label`/`probability`; `Activity.id` with `activity_id` on references. The `shared/contracts.py` Pydantic definitions are authoritative; JSON examples are illustrative. Import these models rather than maintaining independent Python definitions. The vision emitter imports these shared models; do not introduce component-specific copies.

## 2. Current architecture

Implemented backend flow (frontend gaps are documented in PRODUCT.md):

```text
Camera → local vision → Supabase seat_state → ProgressEvaluator
→ EscalationEvaluator → EvaluationRouter → ContextEnricher → Deep Agent
→ teacher_reviews → dashboard handoff / Photon-Spectrum → teacher resolution RPC
```

- Camera frames stay local. The LLM never receives images/video; only structured state leaves the perception boundary.
- HSEmotion is supporting context only, never independent evidence of task struggle.
- Teacher approval is required before changing a task, instruction, or support intervention. Notifications do not require approval.
- Current checkout implements local vision, a continuous agent worker, persistent teacher reviews, Spectrum notifications and a Next.js dashboard. Frontend review/RPC wiring and person-ID visibility remain gaps.

- Groq openai/gpt-oss-20b is the demo model. Keep core routing, contracts and tools provider-independent through injected models.

## 3. Explicitly out of scope

Do not reintroduce any of these unless explicitly requested: ESP32, Arduino, LEDs, physical help buttons, YOLO, MobileNet, object-state recognition, Amazon Bedrock, whole-classroom tracking, face recognition, automatic diagnosis, or emotion-based behavioral scoring.

Voice/push-to-talk is optional future work; dashboard activity selection uses sessions.current_activity_id.

## 4. Dependency management

- Python: use `uv add <package>` at the root. Commit both `pyproject.toml` and `uv.lock`. Never use `pip install` as the project dependency workflow.
- Frontend: run `npm install <package>` inside `web/`. Commit both `web/package.json` and `web/package-lock.json`; use `npm ci` for installation from the lockfile.
- Add dependencies only when needed for the requested task. Do not upgrade unrelated packages.

## 5. Python environment

Read `.python-version` first (currently 3.11). Run `uv sync` at the root, then execute Python commands with `uv run ...`. Keep one shared environment: no second Conda environment, Poetry project, per-component Python project, or standalone `requirements.txt`.

Known entry point, from the root:

```bash
uv run uvicorn vision.app:app --host 127.0.0.1 --port 8000
```

Use `CUES_CAMERA=fake` for camera-free startup. `/health` and `/stream` exist; keep the image stream local. Do not invent other FastAPI entry points or treat PRD example endpoints as implemented.

## 6. Git discipline

Before editing:

```bash
git status
git branch --show-current
```

- Preserve other developers' changes. Do not delete unrelated files, reset their work, force push, merge without an explicit request, or modify another component unnecessarily.
- Keep changes and commits scoped to the assigned task. Follow the personal-branch workflow in `notes/archive/TEAM_WORKFLOW.md` and `.github/pull_request_template.md`; identify cross-owner changes in the PR.
- `main` is the integration branch. Keith works on `keith`, Evan on `evan`, and Michelle on `michelle`. A branch name does not imply a same-named directory exists.

## 7. Code ownership / boundaries

Inspect the actual tree before adding or assuming directories. Integration is shared by all three teammates.

| Area | Responsibility |
|---|---|
| Vision — Keith (`vision/`) | Webcam input, MediaPipe, normalized landmarks, local gesture templates, nearest-neighbor match score, HSEmotion, tracking state, structured perception events. Keep agent logic out. |
| App backend — Evan | App-facing APIs, Supabase schema/integration, realtime product state, and app support for teacher decisions. Current local vision FastAPI service remains in Keith’s `vision/`; no separate app backend directory exists yet. |
| Agent / routing — Michelle | Event routing, rules, alert cooldowns, Deep Agents, LLM integration, tools, intervention decisions, Photon, agent approval workflow. Operates on structured state, never camera frames. |
| Frontend — Evan (`web/`) | Teacher dashboard, station UI, realtime display, task selection, voice controls, alert approval/dismissal, gesture recording controls. Current dashboard integration; persistent review UI wiring remains a gap. |

Event/table changes affect shared contracts in PRD §17. Update affected components and the PRD together and record Keith, Evan, and Michelle's sign-off in the PR, per `CLAUDE.md`.

## 8. Agent behavior requirements

The Cues support agent acts through tools, rather than a single free-form chatbot response. Preferred tool concepts (not claims of existing implementations):

```text
get_session_state
get_recent_attempts
get_support_preferences
choose_intervention
create_teacher_alert
notify_teacher
record_teacher_decision
apply_approved_intervention
```

The agent chooses which tools to call; it need not call all tools for every event. Rules invoke it only for meaningful events with seat/reason cooldowns. Restrict interventions to the approved menu; apply them only after teacher approval and log decisions/actions. Provider failures are isolated and surfaced; do not fabricate a fallback review.

Photon messages contain minimal structured information: no images, raw camera data, expression labels, diagnoses, or unnecessary personal details.

## 9. Facial-expression requirements

- Use `hsemotion-onnx` with `enet_b0_8_best_vgaf`, locally.
- Preserve native expression probabilities; never discard classes and renormalize to five.
- Smooth noisy outputs over time. Store meaningful `expression_context` events rather than a history of the live distribution.
- Call output facial-expression context/model probability, never a diagnosis or knowledge of how a student feels.
- Expression alone must never determine task failure or trigger a task-struggle alert. It may increase the priority of an established task-difficulty event.

## 10. Gesture-matching requirements

- Use MediaPipe landmarks, normalized coordinates, nearest-neighbor matching, and per-activity calibration for custom static gestures.
- Call the derived distance-based value a **match score**, not a probability unless a calibrated probabilistic model is explicitly implemented and validated.
- Record 3–5 target demonstrations; keep templates on the station laptop. Do not impose one universal threshold across activities.
- Tracking loss is not student failure: pause progress timers and exclude lost tracking from miss counts. Record misses only for valid, stably tracked attempts.

## 11. Privacy and configuration

- Never upload student camera frames, face crops, recordings, or raw camera data to Supabase, any LLM provider, LangChain, Photon, or other cloud APIs.
- Use only simulated student data during the hackathon. Identify seats by position, not biometric identity.
- Preserve `.gitignore` protections for local templates, captures, weights, logs, and secrets. The documented developer-recorded built-in `thumbs_up.json` exception contains no student data; do not generalize it to student templates.
- See STARTUP.md for the env split: backend Supabase/Groq in root .env, browser-safe configuration in web/.env.local, and backend-only Spectrum project credentials/destination in cues/.env. Never expose secrets in NEXT_PUBLIC_*.
- Current vision client loads the root `.env` and reads `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`. Station/session/camera settings may also be set there or in the shell; do not introduce a second credentials convention.

## 12. Verification and feature flags

Run checks relevant to changes. Existing vision CI commands, from the root:

```bash
uv run pytest vision shared/tests
uv run ruff check vision shared
uv run ruff format --check vision shared
```

Hardware tests are skipped by default; `CUES_HARDWARE=1 uv run pytest vision` opts in. Record manual camera/model/Supabase/Photon verification still needed. Frontend has `npm run lint` and `npm run build` inside `web/`; inspect scripts before assuming other checks.

Follow `CLAUDE.md` for feature flags: add needed entries to `flags.json`, default new features off until verified, and verify the flag-off fallback. Infrastructure needs no flag. The vision helper (`vision/flags.py`) and vision module gating exist; the vision event emitter sends to Supabase only when `vision.supabase_events` is on and credentials are set. The web flag helper is implemented; the agent worker is explicitly started through its runtime entrypoint.

Before a requested merge, follow the pre-merge review procedure in `CLAUDE.md` and require passing applicable CI, resolved blocking findings, and explicit team authorization to merge. Keep unrelated refactors out of the task.
