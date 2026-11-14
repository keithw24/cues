# TeacherReview read integration — pending backend persistence

The Attention queue now reads only Supabase `public.teacher_reviews`. It does not
read the Python process or the legacy `alerts` table, infer reviews from seat
status, rerun eligibility/routing logic, or offer confirm/dismiss actions.
The existing seat-state feed and its styling remain separate and unchanged.

## Expected read projection

`web/lib/teacher-reviews.ts` defines the minimal flattened projection used by the
UI, based on the existing TeacherReview/AgentEvaluationRequest/AgentAssessment
models inspected on `origin/main` (`4dfb591`). This is a proposed consumer contract
for Michelle's persistence work, not a claim that a migration/table exists.

| Column | Expected type | Trusted backend source |
| --- | --- | --- |
| id | UUID string | TeacherReview.id |
| session_id | UUID string | evaluation.session_id |
| seat_id | nonblank string | evaluation.seat_id |
| activity_id | nonblank string | evaluation.activity_id |
| created_at | timezone-aware timestamp string | TeacherReview.created_at |
| priority | normal / elevated | evaluation.escalation.priority |
| decision | continue_monitoring / teacher_review_warranted, nullable | assessment.decision |
| rationale | nonblank string | assessment.rationale |
| evidence_used | string array, nullable/empty when absent | assessment.evidence_used |
| status | pending / confirmed / dismissed | persisted review lifecycle |
| resolved_at | nullable timezone-aware timestamp | future resolution lifecycle |

The backend stores pending/confirmed/dismissed review lifecycle states, as confirmed
by Evan. Assessment decision is a separate field, copied from assessment.decision;
it is never inferred from lifecycle or seat state. Missing/unrecognized decision
values display 'Decision unavailable'. Persistence must expose a decision column
for the explicit read projection; no nested assessment/model trace is requested.

Evidence labels preserve the backend enum: current_progress, activity,
recent_progress_history, prompt_history. The UI translates these to teacher-facing
labels without inventing an evidence finding or exposing raw expression output.
The rationale is rendered as plain text, never HTML.

## Subscription and lifecycle

- Initial SELECT reads only the explicit columns above with status=pending.
- A separate Supabase channel subscribes to all INSERT/UPDATE/DELETE changes on
  this table. It deliberately has no pending-only event filter: an item leaving
  pending must still cause a refresh.
- Valid INSERT/UPDATE payloads reconcile immediately by review ID. Pending rows
  appear/update in the queue; confirmed/dismissed rows disappear immediately.
  DELETE payloads remove the matching primary key immediately. The selected detail
  panel uses this same queue snapshot, so updated assessments replace its content
  and resolved/deleted reviews become the existing no-longer-pending state.
- Events also debounce a pending snapshot reload by 100ms. Partial/incompatible
  payloads fall back to this authorized SELECT instead of fabricating review data.
- Events and SUBSCRIBED callbacks invalidate reads started before them. A stale
  response is discarded and followed by another read, preventing a resolved review
  from reappearing or a new insert from being hidden by an older snapshot.
- Duplicate events replace rows by ID instead of appending. Reconnect snapshots
  replace the queue; they are never concatenated with cached rows.
- Every SUBSCRIBED callback reloads the snapshot, including reconnection. Online
  recovery recreates the subscription; cleanup aborts reads and removes channels.
- One fetch runs at a time; a change during a read queues a follow-up fetch.
- UI order uses backend priority (elevated first), then oldest created time/id.
  It never recalculates urgency or validates the backend's routing decision.
- On failure, the last snapshot is retained with an explicit stale-data warning;
  without a snapshot the UI says unavailable, not 'no pending reviews'.
- Seat/activity names use accessible metadata when available; identifiers remain
  visible as fallbacks. Activity lookup uses the review's activity identity, not
  whatever the seat is currently doing. Unknown seats are not silently dropped.

## Flag and backend rollout

`web.teacher_reviews` defaults false. Set `CUES_FLAG_WEB_TEACHER_REVIEWS=1` in the
local environment after the backend hookup is ready (and rebuild production).
Flag off makes zero review reads/subscriptions and shows 'not connected'; it does
not restore the removed simulated/seat-status queue. `web.dashboard` still gates
all dashboard code as before.

Michelle-side prerequisites remain pending:

1. Agree/finalize this flattened projection and implement its migration.
2. Persist trusted review objects from request_teacher_review/TeacherReviewStore
   into teacher_reviews using backend credentials and appropriate idempotency.
3. Grant SELECT through an explicit authorized RLS policy. Scope reads to the
   teacher/station/session or an explicitly restricted simulated demo. The UI
   displays pending rows accessible to its Supabase role; browser filtering is
   not authorization. This checkout currently has a publishable demo client and
   no authenticated-teacher sign-in flow.
4. Add teacher_reviews to the Supabase Realtime publication and verify row changes
   reach authorized subscribers. Read authorization must not hide resolved rows
   solely because status is no longer pending, or exits may be missed until resync.
5. Keep trusted identity/priority/rationale/evidence backend-owned. Do not grant
   blanket browser INSERT/UPDATE/DELETE. Future teacher actions require a separate
   narrowly authorized transition path; no action path is implemented here.

No Supabase migration, grants, shared contracts, agent code, FastAPI route or
separate WebSocket transport was added by this frontend change. The actual table
hookup cannot be claimed verified until those prerequisites are deployed. No
service-role secret is exposed in browser code.

## Verification

`npm run lint`, `npm test` (17 tests), `npm run build` pass from web/. Both review-flag
builds and 3 shared flag-registry tests passed. Tests cover the flag-off
no-network fallback, trusted projection validation, priority ordering, initial
read/reconnect, status exits/deletes, errors/stale snapshots, cancellation and
unsubscription, plus the unchanged seat feed tests. Browser verification uses
isolated intercepted synthetic rows when the real table is unavailable; such
fixtures do not create persisted reviews or prove deployed Realtime wiring.

The video box is independently fixed to 4:3 landscape at all breakpoints;
image content remains contained without stretching.

Browser checks verified the projection/order, absence of approval/dismiss buttons,
resolved exits after synthetic online resync, independence from seat review status,
missing-table error/retry, and flag-off zero review reads. These use isolated REST
fixtures, not deployed table writes. The preview was restored to the flag-off build.

## Persistent action adapter (supersedes read-only action notes above)

The frontend now provides **Needs attention** → confirmed and **Dismiss** → dismissed,
behind the additional default-off `web.teacher_review_actions` flag
(`CUES_FLAG_WEB_TEACHER_REVIEW_ACTIONS=1`). The review feed must also be enabled.
The old visit-local dismissal path remains removed. Neither localStorage nor seat
status supplies a review resolution.

**Prepared transport contract; deployment/security still required:**
`POST /rest/v1/rpc/resolve_teacher_review` via Supabase `.rpc()`, with only
`review_id: UUID` and `action: confirmed | dismissed`. Return a one-row array
matching the read projection, including the persisted status and server-generated
resolved_at. A missing RPC, denied access, empty result/conflict, malformed result
or timeout is a failure. No unrestricted browser table update is used.

The deployed action boundary must map confirmed to
`TeacherReviewStore.confirm_needs_attention(review_id)` and dismissed to
`TeacherReviewStore.dismiss_review(review_id)`. Evan confirmed these methods exist
on both in-memory and Supabase-backed stores. Do not bypass their semantics with
browser table updates. It must authenticate/authorize the teacher against the
review's session; atomically compare status=pending and update status/resolved_at
only; reject invalid targets and already-resolved reviews; protect all trusted
fields; and return the committed row. Do not grant anonymous execute or broad
UPDATE rights to make this demo work. The current dashboard has no teacher login,
so authorization/session integration remains a deployment prerequisite. No SQL
function or permissive grants have been invented against the absent schema.

Both buttons lock during a request and show Saving… on the chosen action. Only a
validated successful acknowledgement removes a row immediately. A short-lived
set of server-acknowledged IDs prevents an older in-flight read from resurrecting
it; it is not a local dismissal store and is lost on refresh. Refresh reads the
persisted Supabase status. Realtime continues to reconcile changes from other
clients. Failures preserve the row with an inline sanitized error directing the
teacher to refresh/check status (a timeout may occur after a server commit).
These actions record teacher triage only; they do not apply an intervention.

Verification: 21 frontend tests pass, including both action mappings, pending-only
client guards, narrow RPC payloads, errors/conflicts and invalid acknowledgements.
Deployed writes, refresh persistence and server-side authorization remain unverified
until backend persistence/RPC and teacher authentication exist. Keep the action
flag off until those checks pass.

After contract alignment, 22 frontend tests pass, including the independent action
flag-off guard. Lint and TypeScript pass. Production build verification for this
increment encountered a local Turbopack worker port-binding restriction.

## Selected-review assessment details

View review opens the existing right-hand panel (below the video/seats on mobile).
The queue keeps only seat, activity, priority, created time and the View review
button. The selected panel shows decision, priority, seat, activity, created time,
concise trusted agent rationale and the evidence source labels. The action buttons
live in this panel and retain their separate deployment flag.

Decision labels: continue_monitoring → Continue monitoring;
teacher_review_warranted → Teacher check-in recommended. Rationale tokens
stalled_progress and stalled_progress_with_expression_context → Repeated stalled
progress (no inference that facial expression establishes struggle). Unknown snake
case rationale tokens become 'additional review context'. Evidence uses the four
existing source-label mappings. Known activity fallbacks raise_hand/thumbs_up become
Raise hand/Thumbs up; unrecognized activities say Activity unavailable.

No raw prompt/history contents, chain-of-thought, nested assessment dumps or model
traces are selected/rendered. prompt_history is only the label 'Previous prompts'.
Back to queue/Escape restores focus to the originating review or the queue heading.
If realtime removes an open review, the panel reports that it is no longer pending;
it does not retain a stale actionable assessment.

## Realtime synchronization verification — November 14

40 frontend tests pass, including immediate inserts, both resolution statuses,
updated assessment data, duplicate events, primary-key-only deletion, reconnect
with missed changes, empty queue, partial payload fallback, and in-flight snapshot
races. Existing seat-feed tests and the review-flag-off fallback still pass. Lint
and TypeScript pass. Production build attempted but blocked by a network fetch of
the existing DM Sans Google Font; no font or dependency changes were made.

No live Supabase review integration is claimed. Once Michelle's authorized table,
RLS and Realtime publication are deployed, enable web.dashboard and
web.teacher_reviews and test two authorized dashboards: create a simulated pending
review, open its details, update its assessment, resolve it to each terminal status,
then disconnect/reconnect one client while another creates/resolves reviews.
Confirm immediate queue/detail changes, one item per ID and the empty state after
the last resolution. Persistent action verification additionally requires the
authorized RPC and web.teacher_review_actions; these gates remain default-off.
