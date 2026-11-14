# Michelle — routing / agent engineering log

# Architecture
```mermaid
flowchart LR
    A[CV observations] --> B[ProgressEvaluator]
    B --> C[ProgressState]
    C --> D[EscalationEvaluator]
    E[ExpressionContext] --> D
    D --> F[EscalationDecision]
    F --> G[EvaluationRouter]
    G --> H[AgentEvaluationRequest]
    H --> J[ContextEnricher]
    J --> I[Future Deep Agent]
```

- **ProgressEvaluator:** Is the student making progress?
- **EscalationEvaluator:** Is this situation worth asking the agent about?
- **Evaluation Router:** Should we invoke the agent now, or have we already evaluated this situation?
- **ContextEnricher:** What task context is missing from the request?
- **Future Deep Agent:** What, if anything, should Cues do?

Add a concise entry here whenever a meaningful routing/agent step is completed.

## Previous work — rolling progress window

We rejected “3 failed attempts” as the primary routing model because a physical
response may be partial, held, hesitant, or gradually improving rather than three
separate attempts. Continuous timestamped observations better represent this.

`agent/progress.py` consumes shared `SeatState` snapshots and returns internal
`ProgressState(trend, stalled_seconds)`. Trends are `improving`, `stalled`,
`completed`, and `unknown`. No shared progress-result contract was added.

Actual implementation: a configurable four-second window compares early/later
half-window score means. Improvement enters at an increase of 0.10 and remains
improving until the increase drops below 0.05. One observation per half-second
bucket bounds memory and limits burst weighting. A boundary observation permits
irregular sampling; only in-window scores enter the comparison. These tunable
score changes are not probabilities or validated learner thresholds.

Stall duration uses observation timestamps from the first valid observation or
last improving evaluation. Incomplete window coverage is unknown. Gesture tasks
require a score; rule tasks use valid observation time without completion, without
inventing a score. Gesture completion uses the supplied activity success threshold;
explicit `done` also completes. Completion is normally latched until reset or a
session/seat/activity change. Duplicate/out-of-order observations do not advance
time; stale input can invalidate state. Future observations are ignored. Invalid
or unknown tracking, missing gesture scores, idle/tracking-lost status, and gaps
over two seconds clear history and reset stall timing. Same-task restarts require
`reset()`. No missing interval counts as student failure. Fresh task timestamps
must not be replaced by unrelated app/expression update timestamps.

The earlier prototype's expression and agent-action fields were removed. The
current progress evaluator neither reads expressions nor requests agent calls.
It does not use `Activity.no_progress_seconds` to decide escalation.

## Current work — deterministic escalation evaluator

`agent/escalation.py` adds a pure function:

```python
evaluate_escalation(progress_state, expression_context=None,
                    *, config=DEFAULT_ESCALATION_CONFIG)
```

It returns a frozen internal dataclass `EscalationDecision` with
`should_evaluate`, `priority` (`normal`, `elevated`, or None), and `reason`
(`stalled_progress`, `stalled_progress_with_expression_context`,
`prolonged_stalled_progress`, or None). False decisions have no priority/reason.
Shared Pydantic contracts are unchanged. Configuration is a frozen validated
`EscalationConfig`; pass the selected object explicitly. There are no demo-mode
branches, external calls, alerts, instructional changes, or cooldown logic.

| Setting | Classroom/default | Accelerated demo |
|---|---:|---:|
| min_observation_seconds | 5 | 2 |
| expression_assisted_seconds | 6 | 5 |
| normal_stall_seconds | 10 | 4 |
| prolonged_stall_seconds | 15 | 6 |

All durations are seconds. No escalation before the minimum. Only `stalled` can
qualify; improving, completed, and unknown cannot, regardless of expression.
Stalled duration is used conservatively as a lower bound on valid observation
time, so no extra observed-duration field is necessary. The prolonged threshold
wins first and yields elevated priority. Otherwise qualifying expression permits
an earlier/elevated evaluation; otherwise the normal threshold yields normal
priority. Threshold comparisons are inclusive. Each call describes eligibility;
repeated calls may return true. Deduplication/cooldowns are future work.

Supporting expression context requires a native anger/fear/sadness model label,
probability at least 0.50, and sustained duration at least five seconds. These
configurable qualification values are unchanged between timing presets. Missing
duration, neutral output, or weak/brief output cannot accelerate evaluation.
This is model context, not a verified internal state or diagnosis. The caller
must supply fresh context for the same task; ExpressionContext has no timestamp,
so this pure layer cannot independently establish freshness. Never reuse stale
context across tasks. Expression cannot bypass the stalled-progress gate.

Demo timings compress live judging delays; they are not classroom recommendations.
The classroom/default progress window remains four seconds. Demo callers explicitly
use `ProgressEvaluator(activity, window_seconds=DEMO_PROGRESS_WINDOW_SECONDS)`;
the named demo constant is two seconds. Expression persistence remains five seconds.
With a continuous valid stalled sequence, normal eligibility at four seconds,
expression elevation at five, and prolonged elevation at six are all reachable.
The demo expression branch elevates priority after normal eligibility; it does not
accelerate eligibility. These timings are for presentation speed only, not classroom
recommendations. Configuration permits either expression/normal ordering while
requiring both thresholds to fall within minimum/prolonged bounds.

Tracking behavior is preserved: the progress evaluator clears invalid history
and returns unknown; escalation cannot advance its own clock or count missing
observations. Consume only freshly updated ProgressState results.

ProgressEvaluator asks: “Is the student making progress?”

EscalationEvaluator asks: “Is this situation worth asking the agent about?”

Future Deep Agent asks: “What, if anything, should Cues do?”

An escalation decision does **not** automatically imply a teacher notification,
that a student needs help, or permission to change instructions.

Verification: 33 new escalation tests cover both presets, non-stalled gates with
and without expression, requested classroom/demo examples, exact boundaries,
weak/brief/missing expression persistence, and invalid configuration/durations.
`uv run --no-sync pytest agent/tests shared/tests vision`: 137 passed, 3 skipped
(camera/model and credential-dependent integration checks). Ruff check passed.
No LLM, Deep Agents, provider integration, Photon, Supabase, endpoint, or alert
cooldown implementation was added. Existing progress changes were preserved.

## Demo timing consistency fix

Kept classroom escalation at 5/6/10/15 and default progress at four seconds.
Changed demo escalation to 2/5/4/6 and added an explicit two-second demo progress
window constant. Kept expression persistence at five seconds. Updated boundary
checks and added a timestamped end-to-end progress/escalation test proving each
demo branch is reachable, plus a short-expression regression test. Verification:
139 tests passed, 3 skipped; lint and formatting passed. No architecture,
shared contract, routing side effect, deduplication, or cooldown was added.

## Evaluation Router — episode-aware request deduplication

The pure EscalationEvaluator answers eligibility on every call; a continued stall
can remain eligible indefinitely. `agent/router.py` separates this from invocation
by returning one internal `AgentEvaluationRequest` or None. It never calls an
agent. No generic time-based cooldown, external service, or shared schema change
was added.

API: `router = EvaluationRouter()` followed by
`router.route(snapshot, progress, decision)`. Supply matched, fresh, ordered inputs
for the same observation. The router does not calculate progress, expression
qualification, or elapsed time. Unknown, invalid tracking, inactive tasks, and
ineligible decisions emit nothing.

State is an in-memory dictionary keyed by `(session_id, seat_id, activity_id)`;
its value is the strongest emitted level in the current logical episode. No
additional episode UUID is necessary. Seats/activities/sessions are independent;
returning to an old identity retains its state unless reset. Improving or completed
clears that identity. Same-task restart or abandoned-task cleanup uses
`reset(session_id=..., seat_id=..., activity_id=...)` explicitly. A new identity
has no inherited evaluated state.

Unknown pauses suppression, even though ProgressEvaluator clears its score history
and timing on tracking loss. This intentionally avoids treating tracking recovery
as a new failure episode. Resumed stalled input can only emit if its decision is
stronger than the previous maximum. An ineligible interval alone does not reset
or consume an episode.

Strength ordering is normal/stalled_progress < elevated/expression context <
elevated/prolonged stall. Each stronger level can emit once; identical decisions,
downgrades, and reappearing previous levels are suppressed. Prolonged can upgrade
expression-assisted elevation despite sharing its priority, because sustained
stall duration is materially stronger evidence. Invalid eligible priority/reason
pairs are rejected without consuming state. At most three requests per episode
are possible with the current model; the first may begin at any level.

The frozen internal dataclass request contains exactly:

- `session_id: UUID`: identifies the session.
- `seat_id: str`: identifies the observed seat without biometric identity.
- `activity_id: str`: identifies the active task; missing activity cannot route.
- `observed_at: datetime`: reuses snapshot.updated_at to tie the request to its observation.
- `progress: ProgressState`: carries current trend and stalled_seconds without duplicating fields.
- `escalation: EscalationDecision`: carries eligibility, priority, and reason using the existing type.

No station ID is added because SeatState has none; no recommendations, teacher
actions, raw camera data, or LLM output are carried. Frozen existing progress and
escalation dataclasses are reused. A returned request means emitted locally,
not successfully delivered or evaluated. Persistence, concurrent access, retries,
and delivery acknowledgments are outside this step; process restart loses state.

ProgressEvaluator = Is the student making progress?

EscalationEvaluator = Is this situation worth asking the agent about?

EvaluationRouter = Should we invoke the agent now, or have we already evaluated this episode?

Future Deep Agent = What, if anything, should Cues do?

Verification: 12 router tests cover first emission, repeated suppression,
improvement/completion reset, unknown/tracking pause, seat/activity/session
isolation, both upgrade paths, downgrades, ineligibility, explicit restart,
missing activity, and invalid decisions. Full suite: 151 passed, 3 skipped
(camera/model and credential-dependent integration checks). Ruff lint passed.
No commit, merge, or push was performed.

## ContextEnricher — deterministic activity context

`agent/context_enricher.py` resolves the task definition missing from the router's
request. The request already includes session/seat/activity identifiers, observation
time, progress, and escalation. No new shared contract is needed.

API: `enricher = ContextEnricher(activities)` accepts an iterable of shared Activity
models; `enricher.enrich(request)` returns the internal frozen dataclass
`EnrichedEvaluationContext(request: AgentEvaluationRequest, activity: Activity)`.
The original request is preserved; the matching activity provides its human-readable
name, check type, and existing activity-specific configuration without inventing
an additional task schema. Activity IDs must match exactly. Missing/unknown IDs
raise KeyError; duplicate catalog IDs raise ValueError rather than silently
selecting one definition.

The catalog is an in-memory validated snapshot. Callers may load the existing
`shared/fixtures/activities.json` with Activity.model_validate; the enricher has
no file/service access or hidden fixture defaults. Construct a new enricher when
the catalog changes. Input activities and returned activities are detached so
mutation cannot affect later requests. The outer result is frozen; its Activity
remains a normal mutable shared model. This does not add historical activity
versioning; callers must supply the appropriate catalog for the request.

No student profile, support preferences, additional expression data, score history,
recommendations, interventions, alerts, LLM output, or external lookup is added.
Activity name is the available task description; no richer instruction text is
inferred for a custom gesture. Enrichment does not change eligibility, router
state, or call an agent. Unknown activity failure is surfaced to the caller;
delivery/retry handling remains separate future work.

Seven focused tests use existing activity fixtures to verify enrichment,
empty/unknown catalogs, isolation across activities and session/seat requests,
deterministic typed output, mutation isolation, and duplicate-ID rejection.
Full suite: 158 passed, 3 skipped (camera/model and credential-dependent checks).
Ruff lint passed. Existing architecture diagram updated in place to include
AgentEvaluationRequest → ContextEnricher → Future Deep Agent; previous notes and
citations preserved. No commit, merge, or push performed.

## First future Deep Agent tool — get_recent_progress_history

Implemented in `agent/progress_history.py` as the documented plain bound callable
`store.get_recent_progress_history(session_id: UUID, seat_id: str,
activity_id: str, limit: int = 10) -> list[ProgressHistoryEntry]`.
A future runtime can pass `store.get_recent_progress_history` in its tools list;
no LangChain decorator, runtime, or model is required here. This is an optional
agent-invoked retrieval tool, not another deterministic routing node. Existing
context enrichment and router behavior are unchanged.

Previously only current evaluator summaries and synthetic observation fixtures
existed; no longitudinal evaluated history was persisted. The new small
`ProgressHistoryStore(capacity=50)` is populated explicitly with
`store.record(snapshot, progress_state)` using matched shared SeatState and
existing ProgressState objects. No automatic pipeline recording is wired up.
Later this in-memory source will be replaced/backed by Supabase; no database or
repository/service abstraction was added now.

The typed internal Pydantic entry has only `observed_at` (the existing snapshot
observation timestamp) and `progress` (reuses ProgressState: trend and
stalled_seconds). Completion is the existing completed trend, not a fabricated
history field. Query IDs select the session/seat/activity and are not repeated
on each returned entry. No raw frame, raw score sequence, expression context,
student profile, prompting history, diagnosis, intervention, or alert is stored.

Retrieval returns the latest N retained summaries in chronological order; default
10 and maximum 50. Capacity is configurable from 1 to 50 per identity. Late
records are sorted by observation time, and older records cannot displace newer
retained ones. Equal timestamps replace their prior summary. Empty history is
an empty typed list, not evidence of success or absence of difficulty. Missing
activity on record is rejected. UUID strings from future tool calls normalize to
UUIDs for lookup. Results are detached from internal storage.

Limitations: recency means latest count, not a wall-clock interval; no counts of
independent stall episodes or interpretation of patterns are inferred. Recording
cadence belongs to the caller: these are evaluator summaries, not frame uploads.
History disappears on process restart; identity keys live for the store lifetime,
so total identity count is not globally bounded. The store is not thread-safe or
cross-process and has no retention-age or task-version semantics. Callers supply
correctly matched observations and evaluator outputs. No support/prompt-history
or teacher-review tool is implemented. Research rationale remains in PRD §12.6
rather than duplicated here.

Verification: 13 focused tests cover recent history, chronological sorting,
per-key capacity and query limits, late records, empty history, isolation across
seats/activities/sessions, deterministic typed JSON round trips, timestamp
replacement, invalid limits, missing activity, and a default query with small
capacity. Full suite: 171 passed, 3 skipped (camera/model and credential-dependent
integration checks). Ruff lint/formatting passed. No commits, merges, or pushes.

## First actual Cues Deep Agent

`agent/deep_agent.py` uses the installed deepagents 0.7.38 create_deep_agent API.
The public factory is `create_cues_deep_agent(model, history_store)`; model is a
required tool-capable LangChain BaseChatModel, supplied by the caller. No provider,
model name, credentials, or environment defaults are selected by Cues. Calling
`agent.assess(enriched_context)` starts a fresh bounded graph run and returns an
internal validated AgentAssessment. `agent.build(context)` exposes the compiled
graph for inspection. Each assessment has fresh message state and no checkpointer.

EnrichedEvaluationContext is serialized using Pydantic TypeAdapter to JSON in the
user message: UUIDs, aware timestamps, enum values, request/progress/escalation,
and the shared Activity definition remain structured. Activity/request ID mismatch
is rejected. No camera data or additional learner profile is supplied.

The assessment has exactly `decision` (continue_monitoring or
teacher_review_warranted) and `rationale` (nonblank, at most 500 characters).
Extra fields and unsupported decisions are rejected. ToolStrategy supplies the
framework's structured-output mechanism; it is not a second domain tool. Invalid
structured output and model/run errors propagate; deterministic alert fallback
and notification handling are not implemented in this step. A 12-step graph
recursion limit bounds a misbehaving run; no timed cooldown is introduced.

### Why this is a Deep Agent

The agent can now gather context with information tools, reason over returned
results, and conditionally call its first action tool, request_teacher_review.
That explicit action creates only a pending review. The teacher can now resolve
it deterministically as Needs attention or Dismiss. This records an attention
decision; instructional-change approval, dashboard APIs and notification remain
future work. The information → reasoning → action sequence is
verified in the actual graph offline and demonstrated live. Successful action now
terminates with its stored assessment and pending review; another LLM turn adds no
value. Some live scenarios still recommend review without selecting the action.
Assessment alone is not action execution.

The agent now exposes two information tools and can choose no tool, progress
history, prompt history, or both. Later steps can depend on earlier tool results;
there is no fixed sequence. Offline graph tests exercise both tools sequentially
in one run. Live Groq runs have demonstrated no-tool, progress-only, and
prompt-only paths; a live both-tools path has not yet been observed. This is a
capability distinction, not a claim that every run should retrieve both.

Live evidence after the context/prompt fix: Groq openai/gpt-oss-20b skipped
history for improving current context, selected history for stalled contexts,
and then used returned summaries in the same run. Repeated stalls led to a
teacher-review recommendation; prior completion led to monitoring. Empty history
was explicitly acknowledged as insufficient to establish a pattern. This observed
adaptive tool use supplements the scripted mechanics tests; it does not guarantee
consistent model behavior across runs. Details and transient failures are recorded
in the live context-fix entry below.

The real create_deep_agent graph lets the injected model choose whether current
context suffices or whether either history tool would materially improve its
assessment. Information-tool results return into the same run for subsequent
reasoning; the model can then conditionally select request_teacher_review.
This information → reasoning → terminal action path is adaptive, with no fixed
tool sequence. Instructional-change approval remains future work.
No subagent or planning workflow is introduced for this narrow task.

The history wrapper binds session/seat/activity IDs to the current request;
only a bounded limit is exposed as a tool argument. It calls the existing store
and returns JSON progress summaries, excluding entries after observed_at. The
model cannot select another seat/session/task through tool arguments. Because
retention is bounded, old as-of data may already be unavailable. History recording
remains explicit. Prompt history and teacher-review tools are not exposed.

System instructions require structured evidence only, prohibit camera access,
diagnosis and internal emotional-state inference, keep expression supporting-only,
and warn that a stall does not imply intervention. History is optional, must be
used when retrieved, and must never be invented. Empty history is missing evidence.
Task text is data, not instructions. Teacher review is a recommendation, never
notification or permission to autonomously change instruction. These semantic
requirements are instructions to the model, not guarantees established by schema
validation; a real model still needs evaluation before product use.

Installed API detail: create_deep_agent adds filesystem/subagent scaffolding by
default. Cues uses its public beta HarnessProfile API on a small BaseChatModel
wrapper identified as cues:assessment, disabling the default general-purpose
subagent without changing global profiles for provider models. Tool binding
forwards to the original injected model unchanged, preserving its actual provider
settings. FilesystemMiddleware is restricted to its mandatory read_file slot;
the scoped profile excludes that tool from model requests and blocks its calls.
No local filesystem backend is supplied. The remaining offered tools are exactly
get_recent_progress_history and the AgentAssessment structured-output mechanism.
These beta configuration APIs should be rechecked on dependency upgrades.

Four offline tests construct the actual graph with a tool-capable subclass of
LangChain FakeMessagesListChatModel. Tests cover direct structured assessment,
serialized enriched context, the exact offered-tool set, real history execution,
its ToolMessage entering the second model step, seat scoping, schema rejection,
and activity mismatch. Scripted fake messages prove graph plumbing, not the
quality of autonomous tool choice or evidence-based rationale by a live model.
No live-provider test was run because no provider/model is selected. The unit
suite uses no paid key or network. Full suite: 175 passed, 3 skipped; lint and
formatting passed. Shared contracts and dependencies were not changed. No other
tools, integrations, subagents, alerts, or instructional actions were implemented.
No commit, merge, or push performed.

## Optional live Groq evaluation — observed run

Added `agent/live_groq_smoke.py`, separate from pytest discovery. Run explicitly:

```bash
uv run python -m agent.live_groq_smoke
```

It loads the ignored root .env without overriding the process environment and
requires GROQ_API_KEY. `.env.example` contains only an empty optional key slot.
No secret values are logged or written. Existing langchain-groq 1.1.3 was already
installed; no dependency change was needed. ChatGroq is instantiated only in the
live script and injected into the existing factory. Default live model is
`openai/gpt-oss-20b`; `--model` permits another evaluation model. Temperature is
zero, retries disabled, request timeout 45 seconds. Core factory, progress,
escalation, routing, enrichment, and history semantics are unchanged.

Two live passes were actually run with synthetic data. Final pass observations:

| Scenario | History called | Structured decision | Rationale observed |
|---|---|---|---|
| Current context sufficient | No | continue_monitoring | Improving trend and zero stalled seconds; model considered current evidence sufficient. |
| Ambiguous stall | No | continue_monitoring | Model cited 10 seconds being below Activity.no_progress_seconds=30. |
| Repeated historical stalls | No | continue_monitoring | Same timeout reasoning; it did not retrieve the prior stalled/improving/stalled summaries. |
| Empty history | No | continue_monitoring | Same timeout reasoning; it never retrieved the empty result. |

The sufficient-context case directly assesses a synthetic recovered/improving
context, deliberately bypassing router eligibility for evaluation only. The other
three share an identical stalled current context and differ in stored history:
prior improvement/completion, repeated stalled/improving summaries, and no entries.
This tests whether the model elects to retrieve missing context without being told
what is in storage. No history call is forced and no scenario-specific instruction
requires a tool sequence. The script prints scenario, structured input, call flag,
actual ToolMessage results when present, same-run followup flag, decision, rationale,
and unexercised history paths. Provider exception bodies/environment values are
not printed; only exception types are logged on failure.

Unexpected behavior: the model consistently treated the activity's 30-second
no-progress setting as sufficient to dismiss further inquiry despite an already
eligible 10-second escalation. It did not inspect repeated historical stalls.
No rationale fabricated specific prior observations; however, “successful
engagement” in the improving case goes beyond the supplied observable trend.
Statements about absence of failure/disengagement should not be interpreted as
verified learner state. These are quality findings, not reasons to silently
change deterministic routing or force tool use.

All four final assessments validated, but this live evaluation did NOT demonstrate
adaptive model-selected history use. When such use occurs, a history ToolMessage
followed by another model step in the same run is the live evidence of adaptive
behavior described in “Why this is a Deep Agent.” Here the repeated-history
rationale path and empty-history handling remain unexercised, not passed. The
script exits 1 for missing history-path coverage (or execution errors), 2 for a
missing key, and 0 only when all requested paths are exercised with valid outputs.
Rationale faithfulness still requires human review; there is no automatic
hallucination judge. A different prompt/model or task configuration can be
evaluated separately, without claiming these baseline results established quality.

Offline tests prove mechanics, including real tool execution and same-run message
feedback with scripted model responses; live tests evaluate actual model judgment
and tool choice. Default offline regression suite: 175 passed, 3 skipped. Ruff lint
and formatting passed for the live script and agent package. No notes were added
until the live run occurred. Existing Deep Agent rationale and citations preserved.
No other tool, provider-specific core change, integration, commit, merge, or push.

## Live Deep Agent context/prompt correction

The initial live failure exposed an agent-facing context bug: Activity's legacy
`no_progress_seconds=30` was serialized even though current progress/escalation
routing does not use it. The model treated this as a second eligibility gate and
never retrieved history. `serialize_agent_context()` in agent/deep_agent.py now
excludes only this activity field and is shared by assess() and the live script.
Shared Activity and ContextEnricher are unchanged. Kept activity id/name/check_type,
success_threshold, and review_threshold, plus all existing request identifiers,
observation time, progress, and escalation. No instruction text was invented.

System instructions now explicitly establish that an eligible routed request
already warrants evaluation: do not re-run thresholds or await another timeout.
If the choice depends on whether the stall is isolated or repeated, retrieve
history; do not infer a pattern or its absence from one snapshot. History remains
optional when current evidence suffices. Never invent observations. Explicitly
prohibit unsupported claims about isolated stalls, learner-specific brevity, or
low stakes. Empty history means uncertainty, not an isolated event. These are
semantic instructions, not deterministic guarantees or new routing rules.

Live reruns used the unchanged four synthetic scenarios and Groq
`openai/gpt-oss-20b`. Initial corrected pass retrieved ambiguous history but still
skipped repeated history and failed on an empty tool message. The domain-tool
wrapper now returns JSON text (including the nonempty string "[]") rather than
a Python list that LangChain can interpret as empty message-content blocks. Store
semantics and records are unchanged. A subsequent pass exercised both ambiguous
and repeated history, but encountered a BadRequestError on the sufficient case
and a RateLimitError before empty-history reasoning finished. After a 45-second
wait, only those two failed scenarios were rerun successfully. `--scenario` now
permits targeted repeats; default still runs all four and preserves all coverage
checks. No failed coverage assertion was weakened and no history call was forced.

Observed successful outcomes across those passes (not one uninterrupted clean run):

| Scenario | History called | Decision | Evidence used |
|---|---|---|---|
| Current context sufficient | No | continue_monitoring | Improving trend, zero stalled seconds, no eligibility flag. |
| Ambiguous stall | Yes | continue_monitoring | Retrieved improving/completed summaries at 02:09:20 and 02:09:40; cited completion before current stall. |
| Repeated prior stalls | Yes | teacher_review_warranted | Retrieved stalled durations 12, 14, 16 seconds interspersed with improving summaries; rationale cited the recurring pattern. |
| Empty history | Yes | teacher_review_warranted | Tool returned JSON "[]"; rationale explicitly said it could not establish whether the stall was isolated or part of a pattern. |

In each successful history case, a real ToolMessage entered the same run before
another model response and validated structured output. The differing rationales
and decisions reflect the retrieved records; no 30-second timeout was used as a
veto. No specific historical event was fabricated in these successful outputs.
Limitations remain: the ambiguous case overstates certainty by calling the stall
isolated, since a small retained history cannot establish all prior behavior.
The repeated case calls improvements brief although only point summaries exist.
The empty case recommends review despite uncertainty; this is a review
recommendation, not proof of need or an automatic teacher notification. Provider
BadRequest/rate-limit failures and nondeterministic tool choices remain possible;
no production retry/fallback policy was added. Live evidence supports adaptive
model-selected tool use when observed, not guaranteed reliability.

Offline regressions assert the timeout is absent from the exact model payload,
criteria/IDs remain, shared Activity is unmodified, and empty history is JSON text
available to the second model step. Full offline suite: 177 passed, 3 skipped;
lint and formatting passed. No new tool/provider, deterministic threshold change,
external integration, commit, merge, or push.

## Lightweight Deep Agent engineering guardrails

Added bounded usage and evidence transparency without changing deterministic
routing, tools, providers, or task contracts. These limits govern latency and
reliability; they are not educational or clinical thresholds. Existing “Why this
is a Deep Agent” and previous live findings remain intact. No new live run was
performed for this step; the new schema and guardrails were verified offline.

Factory API remains model-injected, with optional
`budgets=AgentBudgets(max_model_steps=4, max_domain_tool_calls=3)`. Installed
LangChain ModelCallLimitMiddleware enforces model-call count; named
ToolCallLimitMiddleware counts history-tool attempts, including duplicates.
Structured-output generation counts as a model step, not a domain-tool attempt.
Budget exhaustion raises the library's explicit limit error; it does not invent
an assessment or notification. No thread/checkpoint limits are needed for these
fresh independent runs. Graph recursion allowance is derived separately (40
steps by default) so middleware nodes do not prematurely consume the four-model
budget. Live script and assess() both use the same run_config and validators.
The model budget counts logical model calls; provider transport retries can make
additional HTTP attempts within those calls.

The history tool defaults to ten entries and rejects limits outside 1–10. Store
retention is unchanged at up to 50 per identity. Up to 50 records can be inspected
locally to filter by request timestamp; only the requested last ten or fewer go
to the model. Identical sequential calls (same limit, including default ten) reuse
a prior successful ToolMessage from the current run instead of rereading storage.
No cache crosses runs. Simultaneous duplicate calls in one model turn may both
read the source; the attempt budget still bounds them. There is no global cache,
retry loop, or generic cooldown.

Prompt explicitly states absence of history is not evidence for escalation,
missing data is not negative evidence, and tool failures/empty results must not
be replaced with invented facts. Neither outcome is hardcoded for empty history:
the observed current episode may independently justify review. Existing privacy,
non-diagnosis, emotional-state, expression-supporting-only, and teacher-control
constraints are preserved.

AgentAssessment adds required constrained `evidence_used` labels:
`current_progress`, `activity`, `recent_progress_history`. At least one unique
label is required, up to three. The assessment validator rejects claimed history
use without a successful nonempty history ToolMessage. Empty, failed, or unqueried
history cannot be listed as evidence. Labels remain model-reported usage; checking
availability cannot prove a rationale faithfully used those records or that the
model did not imply unsupported facts. This is an inspection aid, not a clinical
or factual correctness guarantee. No new data is sent as evidence.

Rationale stays capped at 500 nonblank characters; prompt asks for 1–3 short
sentences, approximately under 200 tokens. Character limits are not an exact
provider-token budget. The optional Groq path now uses a 20-second per-request
timeout and the existing SDK retry mechanism with max_retries=2 for transient
failures (up to three transport attempts per request). Not every provider error
is retryable. There is no indefinite retry or whole-agent replay; exceptions are
still surfaced and logged by type only. Overall duration may exceed 20 seconds
across retries, backoff, and multiple model steps. No provider logic was added to
the core factory; no API calls are made by default unit tests.

Twelve added offline cases verify missing-history evidence rejection for either
decision, constrained/unique evidence labels, rationale bounds, ten-entry tool
output, identical sequential query reuse, exact model/tool limit errors, the
four-model default in isolation, oversized history limit rejection, and history
availability validation. Existing direct and multi-step tool paths still pass.
Full suite: 189 passed, 3 skipped (camera/model and credential-dependent checks).
Ruff lint and formatting passed. Files changed in this step: agent/deep_agent.py,
agent/live_groq_smoke.py, agent/tests/test_deep_agent.py, and this log. No new tools,
integrations, subagents, commits, merges, or pushes.

## Second future Deep Agent information tool — get_prompt_history

Implemented standalone in `agent/prompt_history.py`, not registered with the
Deep Agent. The guardrail section above already documents all requested budgets,
context/output limits, evidence semantics, and timeout/retries; no duplicate
section or change to those guardrails was needed.

No structured prompting observations, prompt levels, or production observation
producer existed. This adds only a small internal typed record and explicitly
populated in-memory store. API:

```python
store = PromptHistoryStore()  # capacity=50 per identity, max_keys=100
store.record(session_id, seat_id, activity_id, entry)
history = store.get_prompt_history(session_id, seat_id, activity_id, limit=10)
```

The retrieval bound method is a documented plain callable suitable for future
tool registration. Each returned frozen Pydantic PromptHistoryEntry contains
exactly `observed_at` (aware timestamp) and `outcome` (independent_correct,
prompted_correct, incorrect, or no_response). Query identifiers scope the records
and are not repeated in each result. These categories may be supplied only when
explicitly observed/recorded by a future producer, or as synthetic development
inputs. Independence must not be derived from a completion/match score. No response
must reflect an observed opportunity/response interval, never missing tracking.
Unknown prompting information is not manufactured into any outcome; leave the
observation unrecorded. No prompt-level/type field is added because no existing
producer records it. Error/no-response categories do not assert whether a prompt
was given; no such inference is made.

Results are chronological, default ten and maximum ten per retrieval. Storage
retains the latest 50 records per session/seat/activity, with configurable capacity
1–50 and configurable identity count 1–1000 (default 100). Default total bound is
5,000 records. Once the identity bound is reached, a new identity is rejected
rather than silently evicting someone else's history. Existing keys remain writable.
Late records are sorted by observation time; equal timestamps preserve insertion
order and do not overwrite distinct observations. There is no automatic deduplication.
Empty history is [], not evidence of failure, independence, or a need for support.
UUIDs and nonblank task identifiers are validated; unsupported fields/outcomes and
naive timestamps are rejected. Returned records are detached from storage.

This records observable response outcomes, not frustration, motivation, diagnosis,
behavioral function, support recommendations, or alerts. It makes no decisions.
Recency is latest-count rather than a wall-clock interval. There is no automatic
pipeline recording, source authentication, task-version model, disk persistence,
or concurrency guarantee. Restart loses history; later this small in-memory source
can be replaced/backed by Supabase. No database implementation or repository/service
abstraction was added. Research rationale remains in PRD §12.6 rather than duplicated.

Nineteen focused tests verify explicit recording/retrieval, order (including late
records and timestamp ties), storage/query bounds, empty history, session/seat/task
isolation, deterministic typed JSON output, and invalid fields, outcomes, timestamps,
identifiers, limits, and configuration. Full offline suite: 208 passed, 3 skipped;
Ruff lint and formatting passed. No live test, agent registration, shared-contract
change, teacher-review tool, external integration, commit, merge, or push.

## Two-tool Deep Agent integration

Registered get_prompt_history alongside get_recent_progress_history. Factory API
adds optional `prompt_history=PromptHistoryStore()`; omitting it creates an empty
local prompt store, preserving existing callers. Core remains provider-independent.
Both request-scoped wrappers expose only limit, bind session/seat/activity to the
current request, return JSON text, and exclude future observations. Prompt retrieval
filters the ten latest source records before returning at most the requested limit;
if newer/future records occupy that slice, older as-of records may be unavailable.
No shared contract or store semantics changed. No teacher-review tool was added.

Progress history describes prior stalls/recovery/completion. Prompt history describes
explicit response outcomes and independence/support, which progress cannot establish.
System instructions distinguish these uses, preserve established routing eligibility,
prohibit invented prompting/levels, and require only materially helpful tools. Unknown
progress with zero duration is missing evidence, not success. No automatic both-tool
sequence is implemented. Instructions were shortened after live tests showed a strong
bias toward the first-described progress tool despite support-oriented questions.

The four-model and three-domain-attempt budgets remain. The installed limiter accepts
only one tool-name filter; a narrow subclass overrides its matching predicate to count
both domain tools together, excluding AgentAssessment output-format calls. This uses
an installed-library internal hook that should be rechecked on dependency upgrades.
Duplicate successful sequential queries reuse prior results separately by tool/limit;
identical arguments on different tools never share cached content. Default/max agent
retrieval is ten entries per tool. Rationale cap and live timeout/retries are unchanged.
Evidence labels now include prompt_history (up to four unique constrained labels).
Validation rejects either history label unless that specific tool returned successful
nonempty data. It does not prove the quality of the model's reasoning from that data.

The optional live script now has six scenarios and logs tool names/order, actual results,
validated decision/rationale/evidence_used, and follow-up model-step coverage. Its
coverage gate requires both tools to be exercised in successful same-run assessments
somewhere across the selected scenarios, rather than forcing a particular per-scenario
sequence. Errors still fail the script. Evaluation questions now explicitly distinguish
progress-pattern and independence/support questions, without revealing stored outcomes
or instructing a tool call. This is a test-harness question, not a new shared field or
an automatic production inference about which context is needed.

Live Groq model: openai/gpt-oss-20b. Latest complete six-scenario pass plus one targeted
retry after 45 seconds (not one clean uninterrupted passing run):

| Scenario | Tools selected | Validated decision / evidence |
|---|---|---|
| Sufficient current context | Neither | continue_monitoring; current_progress |
| Ambiguous isolated stall | Progress only | teacher_review_warranted; current_progress + recent_progress_history |
| Repeated stalls | Progress only | teacher_review_warranted; recent_progress_history |
| Prompt-support pattern | Prompt only | teacher_review_warranted; current_progress + prompt_history |
| Mixed ambiguous | Prompt only | Initial RateLimitError; retry teacher_review_warranted, current_progress + prompt_history |
| Empty histories | Progress only | Returned []; final evidence claim rejected with ValueError on both attempts; no validated assessment |

Repeated-stall reasoning cited the actual interleaved stalls/improvements. Prompt-support
reasoning cited one independent correct response followed by three prompted-correct
responses. Mixed reasoning cited the observed correct/incorrect/prompted/no-response
sequence. Thus the selected tool results affected the next model step and final rationale.
No live case selected both; this remains optional, mechanically verified offline.

Limitations: generic stalled contexts sometimes skipped retrieval entirely; explicit
assessment questions changed tool choice. Earlier runs incorrectly treated unknown
history as absence of prior stalls. Latest ambiguous reasoning used absence of a
subsequent recovery observation to justify review, which overstates sparse data.
Empty results still prompted unsupported history evidence labels; the validator correctly
refused them instead of silently accepting/removing labels or weakening assertions.
Both tools were independently demonstrated in successful live runs, but the live suite
still exits 1 due to the empty-history quality failure. No retries beyond existing
transport limits plus the documented targeted rerun were added. Model judgment is not
reliably established by passing schema/mechanics tests.

Offline additions verify both registered tool names, prompt results returning to the
same model run, rejection of unqueried/empty prompt evidence, a shared cross-tool attempt
budget, both-tools sequential execution, and tool-specific duplicate reuse. Full offline
suite: 213 passed, 3 skipped. Ruff lint and formatting passed. Prior notes/citations are
preserved. No provider-specific core configuration, new provider, subagent, integration,
commit, merge, or push.

## Empty-history evidence semantics and one-shot repair

The remaining live bug confused “tool called” with “evidence obtained”: a model
could receive [] and still cite that source in evidence_used. The strict validator
continues to reject empty, failed, or unqueried history. Added explicit system
instructions that calling a tool does not make it evidence, only nonempty usable
information may be cited, and missing data must not become unsupported claims.
Neither assessment decision is forced by an empty result.

`EvidenceValidationError` now identifies only an otherwise schema-valid assessment
with unavailable history labels. A small after_model middleware validates output
inside the existing graph. On the first such error it records a run-state repair
flag, clears structured_response, sends a correction message naming the validation
issue and actually available source labels, and jumps back to the same model node.
The model must reconsider rationale and evidence_used and return one corrected
structured assessment; application code never strips labels or selects a decision.
A second invalid claim raises; malformed schema, provider errors, and unrelated
failures are not given this repair. A repair response without structured output
also fails rather than continuing a tool/retry loop.

This is not a new graph invocation. Model/tool counters, messages, and duplicate
query reuse remain in the same run. Hook ordering matters: the existing model
counter updates before the repair jump, so correction cannot evade the four-call
limit. If no model budget remains, the next attempt raises the installed model-limit
error; no budget is increased or reset. The repair message requests no new tools.
The three-domain-attempt cap, history bounds, 500-character rationale cap, and
20-second Groq timeout/up-to-two transport retries remain unchanged. No factory API
or shared contract changed. Live logging adds evidence_repair_attempted.

Six additional offline cases cover empty progress/prompt source correction,
validated repaired output, second-invalid-output failure with no infinite retry,
repair refused when model budget is exhausted, repair fitting exactly within four
calls, and valid nonempty history finishing without repair. Existing strict
standalone validation tests remain. Full offline suite: 219 passed, 3 skipped;
Ruff lint/formatting passed.

Live rerun used the existing six scenarios and Groq openai/gpt-oss-20b, with no
forced calls or weakened validators/coverage checks:

| Scenario | Tools | Validated decision | Repair |
|---|---|---|---|
| Sufficient current context | Neither | continue_monitoring | No |
| Ambiguous stall | Progress | teacher_review_warranted | No |
| Repeated stalls | Progress | teacher_review_warranted | No |
| Prompt-support pattern | Neither | continue_monitoring | No |
| Mixed ambiguous | Neither | continue_monitoring | No |
| Empty histories | Progress (returned []) | continue_monitoring | No |

The empty-history result explicitly acknowledged absent prior data and returned
`evidence_used=["current_progress"]`. This resolves the targeted live failure in
this observed pass without needing correction; one-shot repair mechanics are
verified offline, not claimed as demonstrated by this live run. The full smoke
script still exited 1 because prompt history was not exercised anywhere in this
pass; that coverage gate remains strict. All six returned schema/evidence-valid
assessments, but coverage and reasoning quality are separate requirements.

Model-quality limitations remain: unqueried prompt data was sometimes described
as unavailable despite records existing in storage, and “brief stall”/lack-of-
recovery language overstates the available context. Label validation cannot prove
rationale faithfulness. No automatic semantic decision override, new tool, provider,
integration, commit, merge, or push was added. Existing Deep Agent documentation,
architecture, prior observed results, and citations were preserved.

## First action tool — request_teacher_review

Implemented `agent/teacher_review.py` and registered the third custom domain tool
in the existing Deep Agent. Progress and prompt history remain information tools;
request_teacher_review is the explicit model-selected action. Returning an
assessment of teacher_review_warranted by itself creates nothing; there is no
hard-coded assessment-to-action mapping.

Model-facing signature: `request_teacher_review(rationale: str,
evidence_used: list[str]) -> str` (JSON review). The wrapper validates the existing
AgentAssessment schema, fixes decision to teacher_review_warranted as the meaning
of this explicit action, and checks evidence availability against actual tool
results before writing. Empty/unqueried history cannot justify a review evidence
label. Session, seat, activity, observation, priority and progress come from the
trusted evaluation request, never model arguments. Semantic correctness of a
rationale is still not guaranteed by source/schema validation.

Internal frozen Pydantic TeacherReview fields:

- id: application-generated UUID, unique per stored review.
- created_at: aware application timestamp (injectable clock for deterministic tests).
- evaluation: existing AgentEvaluationRequest, preserving session_id, seat_id,
  activity_id, observed_at, trusted escalation priority/reason, and progress.
- assessment: existing typed AgentAssessment, providing concise teacher-facing
  rationale, review recommendation, and constrained evidence labels.
- status: pending on creation; confirmed/dismissed after explicit teacher
  resolution, with resolved_at (see the teacher-resolution section below).

No separate suggestion/recommendation schema or speculative student fields were
added. The unchanged AgentAssessment moved to internal agent/assessment.py to
avoid a circular dependency between the agent and review storage; deep_agent.py
still re-exports it for existing callers. Shared contracts are unchanged.

`TeacherReviewStore(capacity=100, clock=...)` holds at most 100 total reviews
(configurable 1–1000), with no external storage. `request_teacher_review(evaluation,
assessment)` creates or returns the first review for an identical complete evaluation
request, including across agent runs sharing the store. Requests with different
observed_at or escalation context are distinct evaluations, not episode-level
deduplication. A lock protects check-and-create from simultaneous duplicate calls.
Full stores reject new requests rather than evict pending work; duplicates still
return their original pending review when full. Resolved evaluations cannot be
reopened by an agent request. `get_pending_reviews()` returns detached copies of
unresolved reviews in insertion/creation order. The store now records teacher
resolution; notification, instruction/intervention changes and dashboard APIs
remain unimplemented.

Factory adds optional `reviews=TeacherReviewStore()`; otherwise the agent instance
owns a fresh store accessible as agent.reviews. Pass the same store to multiple
agent instances when cross-run deduplication/pending retrieval is needed. In-memory
state disappears on restart. An already created review survives a later model/run
failure or a differently worded final assessment; action execution and final text
are separate, without rollback or delivery guarantees. Final assessment is not
teacher approval. No Photon or Supabase call occurs.

All three tools share the existing three-domain-attempt budget. The four-model-call
budget, bounded retrieval, query reuse, rationale cap, evidence validator/one-shot
repair, and live Groq timeout/retries remain. Action output is not a new evidence
source. System instructions explain the explicit pending-review action and human
control; no forced sequence or auto-approval was introduced.

Ten additional offline tests cover pending fields/identity and typed JSON output,
unique IDs, capacity, duplicate reuse when full and within a graph run, detached
retrieval, rejecting approval states/ineligible inputs, no review from assessment
alone, real history → action → final-model flow, shared action/tool budgets, and
unavailable-evidence rejection before creation. Full offline suite: 229 passed,
3 skipped; lint and formatting passed.

Optional live Groq smoke adds review_action using repeated synthetic stalled
history and a conditional review question (no forced tool_choice). It logs all
information/action calls, review_action_called, stored review JSON, and final
assessment/evidence. Run: `uv run python -m agent.live_groq_smoke --scenario review_action`.
Actual observed run with openai/gpt-oss-20b: no tools selected, no pending review,
continue_monitoring, evidence_used=[current_progress]. Rationale asserted no evidence
of prompting/independence issues without retrieving history. Thus live action use
remains unexercised, and the unchanged information-tool coverage gate exited 1;
this was not weakened into a passing result. The offline actual-graph test proves
execution plumbing, not reliable autonomous live action choice. No repeat was
forced to obtain a preferred outcome. Prior notes/research/citations preserved;
no commit, merge, or push.

## Targeted live information-to-action evaluation

Added `prolonged_review_action` to the optional Groq smoke script. Run with
`uv run python -m agent.live_groq_smoke --scenario prolonged_review_action`.
The synthetic current episode has a 30-second stall and trusted elevated
`prolonged_stalled_progress` eligibility. Prior summaries show 25-, 30-, and
35-second stalls at separate timestamps; available prompt outcomes are
`prompted_correct`, `prompted_correct`, `no_response`. The question requests an
assessment and conditional pending review without prescribing tools or sequence.
Core agent configuration, routing, budgets, and offline tests are unchanged.

Observed with `openai/gpt-oss-20b` on November 14, 2026: the first attempt ended
in `APIConnectionError` before tool use. One unchanged retry after verifying
connectivity selected `get_recent_progress_history` → `request_teacher_review`.
The history returned all three recorded stalls; prompt history was not retrieved
and was not claimed as evidence. The action used
`evidence_used=[current_progress, recent_progress_history]` and the rationale:
“Prolonged stall with increasing stalled seconds over 3 minutes suggests persistent
difficulty; teacher review may help adjust support.” The repeated stall pattern
is supported, but “3 minutes” overstates the actual two-minute span from the
earliest returned observation to the current episode. This remains a live-model
factual precision limitation, not something the evidence-source validator proves.

The action created review `66b99951-d73b-438c-be12-1eecfc426213`, status `pending`,
created at `2026-11-14T05:30:01.349218Z`. Its stored assessment was
`teacher_review_warranted`. The complete stored evaluation matched trusted app
state: session `00000000-0000-0000-0000-000000000001`, seat `SIM-A`, activity
`raise_hand`, priority `elevated`. The model supplied rationale/evidence only;
identifiers, priority and status came from application state. The script now logs
`created_review_context_verified` by comparing every created review's evaluation
and pending status with the bound request. No notification, approval, dashboard
write, or instructional change occurred. This local store is ephemeral.

This live Deep Agent demonstrated **information gathering → reasoning over tool
results → conditional action-tool use**. However, after the successful action,
the run raised `ModelCallLimitExceededError` at the unchanged four-call budget.
There was no validated final assessment (`decision`/`rationale` remained null in
the report); the stored action assessment must not be presented as a final run
assessment. The pending action survived that later failure as designed. Thus the
information-to-action path succeeded, while complete run termination remains
unreliable. The smoke command honestly exited 1; its unchanged coverage gate
also requires error-free runs exercising both information tools. No guardrail
was weakened or additional retry used to obtain a preferred decision.

Verification: full offline suite **229 passed, 3 skipped**; existing tests unchanged.
The live fixture and notes are the only files edited for this targeted step.

## Terminal review action and temporal wording reliability

Successful `request_teacher_review` is now terminal. The action is registered
with the installed LangChain `return_direct=True` option and returns its JSON
plus a trusted typed `TeacherReview` artifact. Terminal middleware copies that
review's **stored** assessment and pending review into final graph state; it does
not generate a new rationale. An action-only batch exits directly. If a model
batches information and action calls together, a before-model guard terminates
before another LLM call or model-limit check. Already scheduled tools in that
batch may complete; duplicate review actions still reuse the same stored review.
Failed actions do not produce a terminal success. The four-model-call and
three-domain-attempt limits, bounded histories, evidence validation/repair,
500-character rationale cap, and Groq 20-second timeout/two retries are unchanged.

`agent.run(context) -> AgentRunResult(assessment, pending_review=None)` exposes
the typed final assessment and optional pending review together. The graph also
returns `structured_response` and `pending_review` directly. Existing
`agent.assess(context)` remains compatible and returns only the assessment.
Monitoring or a review recommendation without the action creates no review.
An existing review's original assessment is preserved when an identical request
is reused. No LLM turn is needed to restate a decision already validated and
stored by the action. This supersedes the previous post-action reasoning flow;
earlier live results above are historical, not current terminal semantics.

Temporal instructions now prohibit timestamp-derived elapsed-span arithmetic,
summing durations or converting them into invented spans. Timestamps establish
ordering. The agent should quote exact deterministic `stalled_seconds` values or
use wording such as “repeated prolonged stalls”; separate snapshots do not prove
continuous stalling between them. No shared/history schema or additional duration
field was needed. This is prompt guidance, not a claim that schema validation can
prove every numerical or educational statement true.

Live rerun on November 14, 2026 with `openai/gpt-oss-20b`:

| Scenario | Selected tools, in order | Result |
|---|---|---|
| `prolonged_review_action` | None | Valid `teacher_review_warranted`, evidence `current_progress`; no action and no pending review. It quoted the supplied 30 seconds without deriving a time span, but introduced an unsupported claim about “typical thresholds for independent progress.” |
| `prompt_support_pattern` | `get_prompt_history` → `request_teacher_review` | Successful terminal result, `teacher_review_warranted`, evidence `prompt_history`, `current_progress`; pending review returned with the exact stored assessment and no post-action model turn. |

The second scenario created pending review
`36b73c5b-ed6c-453f-b12a-01765e5e4cd0` at `2026-11-14T05:35:53.581976Z`.
Trusted evaluation context matched session `00000000-0000-0000-0000-000000000001`,
seat `SIM-A`, activity `raise_hand`, priority `normal`. Its final/stored rationale:
“Student achieved independent correct only once, then required prompting for
subsequent attempts while progress stalled, indicating a need to review support
levels for this task.” No unsupported time-span claim or model-budget exhaustion
occurred. The smoke script checks final review/assessment equality with stored
state and logs `post_action_model_turn=false` and
`created_review_context_verified=true`. No notification, approval or instruction
change occurred; reviews remain in an ephemeral local store.

Command: `uv run python -m agent.live_groq_smoke --scenario prolonged_review_action --scenario prompt_support_pattern`.
The terminal fix was demonstrated live in the prompt-history scenario, but the
requested prolonged-stall scenario did **not** select the action. Autonomous
action selection remains variable. The unchanged suite coverage gate exited 1
because progress history was not selected across these two runs; it was not
weakened into a pass. No repeat was forced to obtain a preferred choice. The live
information → reasoning → terminal action path is demonstrated, while reliable
tool selection and factual quality still require evaluation.

Offline verification: **235 passed, 3 skipped** across the full suite. Tests
cover no post-action model call, typed pending-review return, original stored
assessment preservation, duplicate actions (including parallel calls), mixed
information/action batches at the model limit, unchanged default budgets, empty
review on monitoring, and explicit temporal instructions. Lint and formatting
passed. These tests prove mechanics and prompt content, not live-model compliance.

## Teacher review resolution — human decision implemented

The existing `TeacherReviewStore` now owns the teacher decision directly; there
is no additional architecture node, state-machine service or Deep Agent tool.
This completes the human-decision portion of the grand plan:

```text
request_teacher_review()
→ pending review
→ teacher: Needs attention OR Dismiss
```

| Teacher choice | Store API | Allowed transition |
|---|---|---|
| Needs attention | `confirm_needs_attention(review_id: UUID)` | pending → confirmed |
| Dismiss | `dismiss_review(review_id: UUID)` | pending → dismissed |

Both methods return a detached typed `TeacherReview`. Confirmation means the
teacher says the student currently needs attention; dismissal means attention is
not needed right now. Neither decision establishes clinical correctness, chooses
support, approves an intervention, or changes instruction. These deterministic
operations are outside the LLM and are not registered as tools.

The review itself records the decision through `status` and the new aware
`resolved_at` timestamp from the existing injectable clock. No second decision
object is needed. Its UUID, created_at, complete trusted session/seat/activity/
priority evaluation, original agent assessment, rationale and evidence are
preserved. Pending reviews require resolved_at=None; resolved reviews require an
aware timestamp at or after creation. Invalid clock output fails without changing
the pending record. Resolution and state checks occur under the existing lock.

Only pending reviews can resolve. A repeat of the same decision or an attempt to
switch a resolved decision raises `ValueError("review already resolved")` without
changing the record or timestamp. An unknown UUID raises `KeyError` for lookup or
resolution. `get_review(review_id: UUID)` retrieves either pending or resolved
records as detached copies. `get_pending_reviews()` filters out both confirmed
and dismissed records and preserves creation order among the remaining reviews.

The in-memory store keeps resolved records within its existing total capacity
(default 100, configurable 1–1000); resolution does not silently delete history
or free capacity. Repeated agent requests reuse a pending record, but reject an
identical resolved evaluation rather than reopening the teacher's decision. A new
evaluation with different observed_at/context remains distinct as before. The
in-memory store is ephemeral; the Supabase adapter is documented in the persistence
section below. No dashboard API, Photon notification or support/intervention
workflow was added. Shared
`Alert` contracts and routing are unchanged; confirmed is an attention decision,
not the existing alert/intervention approval status.

Verification: full offline suite **327 passed, 4 skipped**. New tests cover both
transitions and resolution timestamps, pending-list filtering/order, preservation
of trusted context and evidence, unknown IDs, all repeat/opposite-transition
combinations, detached lookups, invalid resolution timestamps, and rejecting
agent reopening of resolved records. Integration tests create a review through
the real agent graph, then disable agent/model/information/action entry points;
teacher confirmation and dismissal still succeed without another model/tool call.
Lint and formatting passed. An initial full run failed the existing wall-clock
vision recorder test (`test_recorder_collects_poses_without_preview`); it passed
in isolation and in the subsequent full run without changing vision code or tests.
No live provider call is needed for this deterministic human-decision step.

## Supabase teacher review persistence

Implemented `agent.supabase_teacher_review.SupabaseTeacherReviewStore(client)`
as another implementation of the existing review lifecycle, without a new routing
or agent node. The `TeacherReviewStorage` protocol describes the same five store
operations; the agent accepts either store through its existing `reviews=`
argument. The core factory's default remains `TeacherReviewStore` in memory,
including the existing bounded-capacity behavior. The runtime factory now resolves
configured persistence and passes that store explicitly (see runtime wiring below).
The core agent and tools never inspect credentials or construct clients.

Both stores provide:

```python
request_teacher_review(evaluation, assessment)  # -> TeacherReview
get_review(review_id)                         # -> TeacherReview
get_pending_reviews()                         # -> list[TeacherReview]
confirm_needs_attention(review_id)             # -> confirmed TeacherReview
dismiss_review(review_id)                     # -> dismissed TeacherReview
```

For the Supabase variant, the database is the source of truth on every call.
New adapter/process instances retrieve the same reviews, without restoring an
in-memory cache. Pending retrieval is paginated to avoid the PostgREST row cap,
ordered by created_at then UUID for ties. These reads are not a transactional
snapshot across simultaneous updates. Unlike the bounded development store,
persistent records are not given an artificial global 100-review cap; no automatic
retention/deletion policy was added, and resolved decisions remain stored.

Migration `supabase/migrations/20261114000300_teacher_reviews.sql` adds
`public.teacher_reviews`. It persists id, created_at, session_id, seat_id,
activity_id, priority, decision, rationale, evidence_used JSONB, status and
resolved_at. The complete trusted AgentEvaluationRequest is also stored as
evaluation JSONB for lossless reconstruction of progress, observed_at and
escalation reason/eligibility. Database constraints and the Python row decoder
check that flattened identity/priority fields match this evaluation. Existing
TeacherReview, AgentAssessment, ProgressState and AgentEvaluationRequest types
remain authoritative; there is no independent database-shaped Python contract.
Shared Alert contracts are unchanged.

Identical complete evaluations are unique across processes. The adapter
normalizes observed_at to UTC for equivalent datetime offsets, and inserts using
`ON CONFLICT DO NOTHING`; it retrieves the first pending review instead of
rewriting its rationale/evidence. A matching resolved evaluation cannot reopen.
Resolution first validates the typed candidate, then updates **only** status and
resolved_at with an atomic `id = ... AND status = pending` condition. Concurrent
resolution has one winner. Unknown IDs raise KeyError, resolved/repeated requests
raise ValueError. A database trigger also rejects trusted-field mutation,
creation in a resolved state, and any transition besides pending → confirmed or
pending → dismissed. Timezone-aware timestamps and resolution-at-or-after-creation
are validated. Neither decision chooses support or changes instruction.

API/network errors raise `TeacherReviewPersistenceError` with sanitized messages;
corrupt/inconsistent returned rows also fail. Failures never appear as empty
pending lists or successful memory-only writes. A network timeout after a database
commit can still leave a persisted action with an uncertain response; retries of
creation reuse the database's evaluation uniqueness constraint rather than
overwriting a review. No new retry policy or delivery guarantee was introduced.

Backend construction uses the existing root credential convention (no new env
variables/dependencies; `.env.example` is unchanged). From the repo root, using an
already configured model and progress-history store:

```python
import os
from dotenv import load_dotenv
from supabase import create_client
from agent.deep_agent import create_cues_deep_agent
from agent.supabase_teacher_review import SupabaseTeacherReviewStore

load_dotenv(".env", override=False)
client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
reviews = SupabaseTeacherReviewStore(client)
agent = create_cues_deep_agent(model, history, reviews=reviews)
```

Apply migration 003 after 001/002 in the Supabase SQL Editor, or use
`supabase db push` with a correctly linked/migration-tracked CLI project. The
migration adds teacher_reviews to `supabase_realtime`; Evan can perform initial
SELECTs and subscribe to INSERT/UPDATE Postgres Changes on that table. The
frontend subscription is not implemented here. Existing demo RLS permits reads
only for a matching seats row with is_simulated=true; unknown/non-simulated seats
remain server-only. Provision a simulated seat matching the review's seat_id to
make a synthetic review visible. Rationale/evidence in these demo rows are public,
so only synthetic data belongs there.

Anon/authenticated browser roles have SELECT only, with no write privileges or
resolution RPC. Backend creation owns identity, priority and assessment; the
teacher path uses only the two deterministic resolution operations after future
backend authentication/authorization. The service-role key stays server-side.
This does not implement teacher identity, dashboard endpoints, real-classroom
authorization, Photon, new tools, or an intervention workflow. No hosted database
changes or Realtime delivery verification were performed in this step.

Verification: full offline suite **350 passed, 4 skipped**. The 23 new tests use
the installed Supabase SDK with httpx.MockTransport (no network or credentials).
They cover row round-trips/typed evidence, restart retrieval, UTC-offset duplicate
reuse/first-assessment preservation, pending pagination, both resolutions,
context preservation, unknown IDs, all re-resolution combinations, resolution
races, API/network failures, corrupt rows, invalid requests, and terminal action
through the real agent graph with the persistent adapter.

The migration and `supabase/tests/teacher_reviews.sql` also passed against an
isolated local PostgreSQL 14 instance: RLS demo-only reads, denied anonymous and
authenticated writes, immutable trusted fields, both status transitions,
re-resolution rejection, conflict-safe duplicate insertion, and publication
membership. Synthetic fixtures rolled back and the temporary server was stopped.
Run the optional SQL smoke with an appropriately privileged database connection:
`psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/teacher_reviews.sql`.
Normal pytest does not require a database. Lint/format checks passed. Hosted
migration application and end-to-end Realtime delivery remain team setup checks;
see `supabase/README.md`. The PRD core-table section documents the new table.

## Hosted migration 003 — applied and verified

On November 14, 2026, migration
`supabase/migrations/20261114000300_teacher_reviews.sql` was applied to the hosted
project using psql against the saved database pooler connection. The existing
file was executed unchanged with ON_ERROR_STOP; no dashboard recreation or schema
redesign occurred. All nine initial-schema tables were already present, and
raise_hand already had check_type=rule/no_progress_seconds=30, matching migration
002. Neither 001 nor 002 was reapplied. This project has no
supabase_migrations.schema_migrations history table; deployment follows the
repository's existing ordered SQL-file workflow, not a newly initialized CLI
migration history. Do not reapply the non-idempotent 003 file.

SQL catalog inspection verified all 12 teacher_reviews columns and their types:
id/session_id UUIDs, seat/activity/priority text, full evaluation JSONB, assessment
decision/rationale text, evidence_used JSONB, status, and timestamptz created_at/resolved_at.
The expected primary key, unique evaluation constraint, status/priority/evidence
checks, evaluation/flattened-context consistency check, and lifecycle trigger are
present. Statuses are pending/confirmed/dismissed; a resolved row requires an
aware resolution timestamp at or after creation.

Hosted `supabase/tests/teacher_reviews.sql` **passed** with its synthetic fixtures
rolled back. It verified demo-only RLS reads, denied anonymous writes, no
authenticated INSERT/UPDATE/DELETE privileges, immutable trusted fields even for
service-role updates, both pending → confirmed/dismissed paths, re-resolution
rejection, conflict-safe duplicate insertion, and publication membership. RLS is
enabled; the only browser policy is demo_teacher_reviews_read for SELECT to anon
and authenticated where the referenced seat is simulated. The hosted project's
existing default privileges also grant DELETE to service_role; that key remains
backend-only. No permissions were weakened or new resolution RPC added.

`teacher_reviews` is in `supabase_realtime` with INSERT and UPDATE publication
enabled. A temporary Python public-key subscription received real events for an
isolated synthetic session, in this order:

```text
INSERT pending → UPDATE confirmed
INSERT pending → UPDATE dismissed
```

The same hosted API probe used the existing SupabaseTeacherReviewStore to create
and retrieve pending reviews, retrieve through a new adapter instance, reuse an
identical pending request, confirm/dismiss persistently, remove each resolved
review from pending retrieval, reject repeated resolution and unknown IDs, and
check that all original trusted context/assessment/evidence stayed unchanged.
Public SELECT of each simulated-seat review succeeded; attempted public rationale
rewrites failed with permissions error 42501. Both lifecycle paths and Realtime
delivery **passed**. The temporary subscription was closed and only the two probe
reviews were deleted using their unique session, IDs and synthetic rationale;
zero probe rows remain. Existing classroom rows were untouched. No model calls,
frontend subscription, notification, instruction change or endpoint was added.

Connection setup used credentials saved locally in `web/.env.local`, including
DATABASE_URL and the existing API variables. The direct endpoint was IPv6-only
and unreachable from this environment; the saved pooler endpoint worked. No
credential value was printed or committed. Root backend Supabase env slots were
empty during verification. The runtime wiring described below now reads the
configured local fallback automatically; deployments can continue using the
documented root/process backend variables. Keep database/service-role secrets
server-side.

There is no remaining hosted schema/publication/RLS blocker for Evan's simulated
classroom read subscription. Evan still needs to implement initial SELECT plus
INSERT/UPDATE subscription and provide matching simulated seat IDs. The probe
rows were removed, so the table may be empty until Michelle's backend explicitly
injects SupabaseTeacherReviewStore and creates actual synthetic demo reviews.
Authenticated/authorized teacher-resolution endpoints remain future work; browser
clients cannot resolve reviews directly. No application code or migration file
changed for this deployment; verification used temporary scripts and the existing
SQL smoke file. Earlier local/offline results remain historical checks, separate
from this successful hosted verification.

## Runtime wiring — persistent review store selected at construction

`agent/runtime.py` is the backend composition point:

```python
from agent.runtime import create_runtime_agent

agent = create_runtime_agent(model, history, prompt_history=prompts)
result = agent.run(enriched_context)
```

It resolves storage first, then calls the unchanged provider-independent
`create_cues_deep_agent(..., reviews=reviews)`. The request_teacher_review tool
still receives only a store; no credential lookup/client construction was added
inside the graph or tool. Existing model/tool budgets, terminal review behavior,
evidence validation and teacher resolution semantics remain unchanged.

Repository inspection found no agent backend server/startup loop. The FastAPI
entrypoint is vision-only. The existing live constructor in
`agent/live_groq_smoke.py` now uses create_runtime_agent instead of unconditionally
creating an in-memory review store. The new module is dependency composition,
not another routing node. It does not implement an event listener, connect CV to
agent invocation, create session/activity state, or add endpoints. A future
backend startup can call this same factory with its injected model/history.

Configuration uses existing variables only: SUPABASE_URL and
SUPABASE_SERVICE_ROLE_KEY. Nonempty process values take priority, then nonempty
root .env values, then web/.env.local as a local fallback matching this checkout's
saved credentials. NEXT_PUBLIC_SUPABASE_URL can supply the project URL when a
backend service-role key is present; public/publishable keys are never substituted
for the backend key. An explicit `env_file=Path(...)` replaces default file
discovery, with process values still taking priority. Empty template values do not
erase a valid fallback. DATABASE_URL is not required by the runtime; it was used
only for migration administration. No .env.example variables or dependencies were
added. Credentials remain local to construction and do not enter model messages,
shared contracts, review rows or client-facing assessment output.

The existing client constructor was moved from vision/supabase_client.py to
shared/supabase_client.py; the vision module re-exports the same cached factory
and retains its existing root-env loading behavior. Agent startup passes resolved
credentials explicitly to this shared factory. Vision's optional-client behavior
and flag-off local operation are preserved, without an agent → vision dependency
or duplicate SDK construction code.

With a complete backend configuration, startup constructs a
SupabaseTeacherReviewStore and performs a read-only SELECT id LIMIT 1 readiness
check against teacher_reviews. Partial credentials, a missing explicit env file,
SDK initialization failure, invalid credentials, missing table or failed
connectivity raise RuntimePersistenceError with sanitized messages. No in-memory
fallback occurs after persistence was configured. Later write/read failures
continue to raise TeacherReviewPersistenceError; the action does not claim a
successful review. The readiness check validates access/table availability;
actual write permission is verified by the action/smoke path, not a startup write.

With neither backend URL nor service-role key, local runtime uses TeacherReviewStore
and logs the memory selection; a frontend URL alone does not configure backend
persistence. `create_runtime_agent(..., offline=True)` explicitly chooses memory
without loading config or constructing a cloud client. Core create_cues_deep_agent
also keeps its in-memory default for direct offline/test callers. The live Groq
runner exposes `--offline-reviews`; otherwise a configured run persists pending
reviews. Its synthetic evaluations now use unique session UUIDs, current times
and simulated seat S1-L, avoiding stale-request collisions. These are test-fixture
identities, not a new session lifecycle. Logs include review_storage and scope
stored review output to the current evaluation; other stored reviews are not dumped.

Optional hosted verification:

```bash
uv run python -m agent.hosted_review_smoke
# Optional explicit file: --env-file web/.env.local
```

This command uses a scripted tool-capable model (no live/purchased LLM call) with
the real runtime factory, Deep Agent graph and request_teacher_review action.
It requires hosted API credentials, retrieves the pending row through a separate
store instance, checks trusted context and assessment, then deletes only its
unique synthetic probe session/rationale and checks that no probe rows remain.
Normal pytest never runs this hosted command.

Actual hosted result on November 14, 2026: **passed**, selected
SupabaseTeacherReviewStore, created pending review
`f97b9168-9cdc-428d-9351-870a370ae22a`, verified pending retrieval and cross-instance
persistence, then removed exactly one probe row. This proves runtime/action
persistence mechanics; it does not make a new claim about autonomous live-model
tool-selection quality. Existing hosted Realtime/RLS verification above remains
applicable; no migration or frontend subscription changed in this step.

Offline verification: **372 passed, 4 skipped**, including runtime selection from
root/web/process/explicit-file config, precedence, explicit offline mode, partial
configuration and sanitized initialization failures, write failures without
memory fallback, absence of credentials in model/review/log output, shared-factory
reuse/vision compatibility, actual graph writes via the runtime/live runner, and
smoke cleanup preserving unrelated rows on success and failure. Lint/format checks
passed. No commit, merge or push.

## Authenticated review-resolution RPC

Migration 004 (`20261114000400_resolve_teacher_review.sql`) is applied to the
hosted project. `resolve_teacher_review(review_id: UUID, action: text)` accepts
only confirmed/dismissed and returns SETOF teacher_reviews: the one-element
flattened row array expected by the frontend, including structured evidence.
The function derives identity from auth.uid()/auth.role(), requires authenticated
execution, and restricts access to simulated-seat reviews matching current demo
read scope. There is no teacher/session ownership relationship in this schema:
**any authenticated user can resolve simulated-seat reviews**. This is an explicit
demo authorization gap, not classroom/session authorization. Non-simulated reviews
are rejected. Real classroom use requires a future ownership relationship/check.

The SECURITY DEFINER function uses an empty search_path, qualified objects, row
locking, pending-only transition, and server clock_timestamp(). It changes only
status/resolved_at; migration 003's immutable-field trigger and direct-write
restrictions remain intact. Unknown, invalid and repeated requests raise errors.
Execute is revoked from PUBLIC/anon/service_role and granted to authenticated.
Python lifecycle methods and agent logic are unchanged.

Hosted rollback SQL tests in supabase/tests/resolve_teacher_review.sql passed:
authenticated confirmation/dismissal, one-row return and trusted-field equality,
invalid/unknown/repeated requests, anonymous execution and direct-write denial.
A separate hosted smoke created a temporary Auth user, signed in through the
public client, called the exact RPC for both actions, decoded each one-row result,
and observed Realtime UPDATE confirmed/dismissed. Trusted fields stayed unchanged.
The temporary Auth user and two synthetic review rows were removed afterward.
No service-role token was used to authorize those RPC calls; admin credentials
were used only for fixture setup/cleanup. Full offline suite: 372 passed, 4 skipped.
Frontend subscription/UI and real session authorization remain separate work.

## Photon/Spectrum notification branch

New Supabase review INSERT winners notify after successful persistence and typed
validation, using an injected ReviewNotifier. Duplicate ON CONFLICT reuse never
notifies, including another backend instance; resolution never notifies. The
in-memory store and a recommendation without the action do not send. No LLM call
or new agent tool/node is involved. Runtime injects the Spectrum adapter using
existing root SPECTRUM_PROJECT_ID/SPECTRUM_PROJECT_SECRET, plus the explicit
SPECTRUM_TEACHER_PHONE destination and optional SPECTRUM_SENDER_PHONE dedicated line.
All remain backend-only. The existing cues/ Spectrum SDK project supplies the
one-shot cues/src/notify.ts sender; no inbound listener or new transport service
was added. Install that project's existing dependencies if absent.

The teacher receives only “Cues: Seat <seat_id> may need attention. Open Cues to
review.” No rationale, evidence, expression, images or intervention instructions
are transmitted. Python passes only the message/review UUID over stdin and project
credentials through subprocess environment. The subprocess is bounded to 25s;
SDK errors/output are captured rather than exposing secrets. Acceptance requires
a nonempty SDK send acknowledgement. This does not prove device delivery.

Notification failure is logged with review UUID/error class, retaining the pending
review and allowing terminal agent success/dashboard retrieval. No rollback or
automatic retry occurs. Insert-winner suppression is an at-most-once attempt
policy, not guaranteed delivery: a crash after commit/before sending or an uncertain
provider response can lose a notification. No outbox or delivery-state schema was
introduced. Review IDs are available to injected transports as idempotency context;
the Spectrum SDK sender does not claim server-side idempotency support.

Live synthetic hosted attempt: review b04b075c-093f-415f-8ade-6272a70234ca persisted
and remained retrievable, but Spectrum adapter failed acknowledgement (one attempt,
zero confirmed acceptances). Delivery is **not verified**. No retry was forced;
only the synthetic probe row was removed by smoke cleanup. Root project credentials
and destination were present; provider-side configuration/line/allowlist and send
diagnostics remain to be checked. Stage-only sender diagnostics were added without
printing SDK errors, secrets or phone numbers. The pending-review persistence and
failure-isolation branch is verified; live Photon delivery remains unresolved.

Offline tests cover new insert/duplicate reuse across stores, persistence failure,
both teacher resolutions, notification failure retaining the review, minimal
message contents, replaceable fake senders, bounded subprocess and secret exclusion.
Full offline suite: **379 passed, 4 skipped**; lint and diff checks passed. TypeScript
sender type-check passed. Used the repository's Spectrum skill and provider contract;
no commit, merge or push.

### Nested Spectrum env and direct delivery diagnosis

notify.ts now loads cues/.env relative to its own module path using Node's
loadEnvFile, independent of caller cwd. Spectrum receives the configured
SPECTRUM_PROJECT_ID/projectSecret explicitly; teacher and optional sender routing
are read from the same backend environment. SDK console output is suppressed;
only credential-presence flags and redacted stage/error diagnostics are emitted.
No credential values or phone numbers were printed.

A direct test from the nested cues project on November 14, 2026 confirmed nested
env loading and presence of project ID/secret and teacher destination. No explicit
sender was configured. Initialization and teacher/space resolution completed;
the send stage failed with the exact sanitized SDK error:
`[spectrum-imessage] Target not allowed for this project`.
No acknowledgement/delivery was verified. The teacher destination must be
registered/allowlisted in this Spectrum project's users before retesting. No
automatic retry was made. TypeScript checking passed. Review trigger semantics,
persistence, duplicate suppression and architecture were unchanged; this direct
send probe created no review rows.

## Citations

These sources support allowing processing time, not treating a few seconds as
failure. They do **not** establish universal Cues timeouts or validate facial
expression routing. Our 5/6/10/15 defaults are conservative engineering choices
informed by these ranges; activity/learner calibration remains future work.
The 2/5/4/6 preset is demonstration-only.

- [IRIS Center, Vanderbilt — Wait-Time](https://iris.peabody.vanderbilt.edu/et/wp-content/uploads/misc_media/fss/pdfs/2018/IRIS_fundamental_skill_sheet_wait-time.pdf).
  The supplied PDF redirects to the current skill sheet. It describes benefits
  of 3–5 seconds across groups including students with disabilities, supporting
  an opportunity to process and begin responding before intervention.
- [NPDC — Prompting: Least-to-Most, Steps for Implementation](https://autisminternetmodules.org/storage/ocali-ims-sites/ocali-ims-aim/documents/PromptsLeasttoMostSteps.pdf).
  Response intervals are initially around 3–5 seconds and should reflect learner
  and task characteristics; initiation and completion intervals can differ.
- [STAR Autism Support — Routine Essentials: Prompting Strategies](https://starautismsupport.com/sites/default/files/CEC_STAR_Inclusion_2025.pdf), page 12 of the booklet.
  Gives 5–10 seconds as an example opportunity to respond before prompting.
- [Johnson & Parker — Effects of Wait Time when Communicating with Children who have Sensory and Additional Disabilities](https://journals.sagepub.com/doi/10.1177/0145482X1310700505), Journal of Visual Impairment & Blindness.
  The abstract describes three participants and 5-, 10-, and 15-second conditions
  compared with a 0–1-second baseline. Responses were more frequent during
  intervention; the implications suggest at least five seconds may help. This
  small communication study does not establish gesture-task escalation thresholds.
- [Stahl — Using Think-Time and Wait-Time Skillfully in the Classroom](https://eric.ed.gov/?id=ED370885), ERIC Digest.
  Supports uninterrupted processing intervals of several seconds rather than
  interpreting immediate nonresponse as failure. The ERIC abstract was verified through search after direct access timed out;
  it describes benefits after at least three seconds of uninterrupted silence.
- [Goodwin et al. — Effective Classroom Questioning, ERIC ED285497](https://files.eric.ed.gov/fulltext/ED285497.pdf).
  Discusses processing/formulating responses, benefits of several seconds of
  wait-time, and context-specific cautions about 20–30-second silent waits.
  This classroom question-answer guidance is not a universal maximum for physical
  tasks or learners who need longer response times.
