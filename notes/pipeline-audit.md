# README pipeline connection audit

This audit follows the current production composition, not fixture runners. No
camera frames/images enter the LLM or progress payload. No teacher/student identity,
score, trend, review outcome, or notification destination is supplied by a demo fixture.

| README edge | Actual connection | Status / limits |
|---|---|---|
| Teacher selects activity → sessions.current_activity_id | SessionControls → changeSession → start_station_activity RPC | Connected. Auth station membership, revision concurrency, DB-owned teacher_id. |
| Camera → MediaPipe/HSEmotion | vision.camera + discovered vision stages | Connected; explicit fake-camera mode is development-only. Camera hardware must be available. |
| Current session/activity → vision | browser default-station RPC → loopback /config → StationSessionSync → pinned frame session | Connected. Pauses before assignment or on expired session lease; no fixed S1 session in managed mode. |
| Vision → seat_state | StatusStage → Emitter queue → SupabaseSink | Connected. tracking_valid false clears task_score. DB rejects stale managed writes. Network failure retains local diagnostic fallback, not claimed hosted delivery. |
| seat_state → ProgressEvaluator | worker → local station provider → active-session/revision-filtered source → pipeline | Connected. Invalid tracking, stale/gapped observations produce unknown, not failure. |
| ProgressEvaluator → ProgressHistoryStore | pipeline records newly accepted summaries | Connected, bounded in-memory history; restart loses longitudinal history. |
| ProgressState → EscalationEvaluator | pipeline directly passes current evaluator state | Connected. README previously incorrectly implied history was escalation input. Expression is supporting-only. |
| Escalation → EvaluationRouter | pipeline.route(snapshot, progress, decision) | Connected. Per-episode eligibility/dedupe; reset on task revision. Not a durable cross-process delivery guarantee. |
| Router → ContextEnricher | request IDs resolve against supplied activity catalog | Connected. Unknown activities fail, not invented. Worker uses vision's local catalog; restart after edits. Hosted activity catalog must also contain selectable activities. |
| Enriched context → Deep Agent | injected Groq demo model; structured prompt, bounded tools/output | Connected. Core factory remains provider-independent. No raw frames or arbitrary emotional diagnosis. |
| History → Deep Agent tools | progress history + prompt history callables registered | Connected adaptively. Prompt history has no automatic live producer; empty data is missing evidence, not an invented support pattern. |
| Deep Agent → request_teacher_review | model-selected action tool, trusted request context injected | Connected. A review recommendation alone does not create a row. Successful action terminates using stored assessment/review. |
| request_teacher_review → teacher_reviews | runtime injects SupabaseTeacherReviewStore | Connected; no silent in-memory fallback when persistence is configured/broken. |
| teacher_reviews → dashboard | owned-session review SELECT + Realtime feed | Connected. Auth ownership enforced; unresolved station feeds pause. |
| Newly persisted review → Photon | store INSERT winner invokes injected notifier | Connected. Not a DB trigger or LLM tool. Failures preserve review; duplicate reuse does not notify. |
| Session → teacher → phone → Spectrum | sessions.teacher_id → profile + matching explicit consent/project → nested Spectrum sender | Connected dynamically in demo; no static fallback. Acceptance is distinct from verified handset delivery. |
| Teacher choice → resolve_teacher_review → confirmed/dismissed | browser action invokes owner-authorized RPC; DB sets resolved_at | Connected. README previously drew statuses before RPC. No autonomous instructional change. |
| Evaluator → live progress → dashboard | SupabaseProgressPublisher → guarded publish_task_progress → seat_state.evaluated_progress → existing Realtime → validated UI projection | Deployed and verified on S2. Migration 012 applied; both local rollout flags enabled. |

## Live progress integrity

Publication occurs before LLM invocation, for accepted observations only. It does not
change vision status, score or updated_at, and the worker does not read its own progress
column, so there is no feedback loop. The SQL update locks the active session and matches
seat/session/activity/revision/exact observation timestamp. A newer vision row, activity
switch or ended session rejects the publication. Recent history contains at most ten
summaries from the current evaluator revision. Browser projection checks matching scope,
tracking validity and a five-second freshness bound. It never advances stalled_seconds
using browser time. Unknown/missing/stale evaluations remain unavailable.

## Intentional configuration, not fabricated runtime data

- Demo uses explicit existing 2s progress / 4s normal / 5s expression / 6s prolonged
  configuration, 0.5s polling. Classroom defaults remain unchanged.
- Groq openai/gpt-oss-20b is the injected demo provider/model; tool budgets, retries,
  timeouts and the 500-character rationale limit are engineering configuration.
- Loopback vision URL/port, camera index default, activity-specific scorers and thresholds,
  and display-label mappings are real transport/task configuration, not fake observations.
- Seed S1 and synthetic test IDs remain in seeds/tests/explicit smoke commands. Default
  station, session ownership, actual teacher phone and runtime seat IDs are dynamic.
- Static-phone mode remains explicit development-only; demo.sh forces dynamic mode.

## Remaining operational limits

There is no continuous history persistence or prompt-history observation producer.
The synchronous model/send path can delay polling and cause a conservative gap reset.
Multiple workers on the same assigned station are unsupported: episode suppression is
local, and stronger evaluations may create additional distinct reviews. No guarantee of
one review per student forever is implied. Camera/model failures and missing hosted
activity definitions are surfaced rather than masked with fixture data.

Migration 012 was deployed after explicit approval; hosted dry-run reports no pending migrations.
Both local flags are enabled. For other installations, after migration deployment,
set CUES_FLAG_AGENT_LIVE_PROGRESS=1 in root .env and CUES_FLAG_WEB_LIVE_PROGRESS=1 in
web/.env.local; restart dev/demo. Then verify visible Improving/Stalled/Completed/Unknown,
tracking-loss handling, activity restart, session end, review actions and physical delivery.

Final real-camera verification: S2-P1 published stalled, stalled_seconds=4.066419,
ten history entries, observation age 1.3s. No synthetic observations were inserted.
