# Progress context: backend read dependency

The detail panels distinguish the existing seat task status from evaluated
progress. Working/Needs Review/etc. come from the current Supabase seat_state
snapshot. They are not aliases for ProgressState.trend. Neither match scores nor
browser elapsed time supply progress, stall duration or history.

## Existing backend source

The current remote integration code (`origin/main`) defines:

- agent/progress.py: ProgressState(trend, stalled_seconds), with trend values
  completed, improving, stalled, unknown.
- agent/progress_history.py: ProgressHistoryEntry(observed_at, progress) and
  ProgressHistoryStore.get_recent_progress_history(session_id, seat_id,
  activity_id, limit=10). Entries are chronological, bounded to at most 50 per
  session/seat/activity; they contain evaluated summaries, not raw frame scores.
- The history store requires explicit record(snapshot, progress) calls and is
  in memory. Its presence is not proof that the running pipeline records it.

The local checkout also contains an older evaluator returning ProgressDecision;
its trend/action values differ. It must not be reimplemented or silently treated
as the newer ProgressState contract by this frontend.

No currently exposed Supabase table/read projection or browser-accessible endpoint
supplies these evaluated summaries. seat_state contains only task status,
match score and observation timestamp; events are not browser-readable and are
not a substitute for the evaluator's history. The TeacherReview evidence label
recent_progress_history identifies an evidence source, not its actual contents.

## Smallest backend/API change

Expose an authorized, read-only boundary around the **existing**
get_recent_progress_history method, scoped to session_id + seat_id + activity_id,
with a bounded limit (10 is sufficient). The transport may be a Supabase RPC/read
projection once summaries are persisted; no extra WebSocket is required. Backend
recording must first publish/retain each evaluated summary intended for display.
Do not grant browser access to raw scores, expression payloads, prompts or traces.

Reuse its existing response entries unchanged:

```ts
// Expected backend data, not a new frontend state machine or deployed endpoint.
type ProgressHistoryEntry = {
  observed_at: string; // aware timestamp
  progress: {
    trend: "completed" | "improving" | "stalled" | "unknown";
    stalled_seconds: number; // backend-supplied, finite, >= 0
  };
};
```

The latest entry can supply 'Latest evaluated progress' and an 'As of' time.
Calling it current requires the backend to record the latest evaluator result;
an evaluation captured when a review was created is historical, not live progress.
A review read must use the review's own scope, even if its seat now has a new
activity/session. An empty result means unavailable history, never success.

Once exposed, the UI should show at most a few recent transitions (e.g.
Completed → Improving → Stalled), optionally collapse adjacent identical trends
for display, and show stalled_seconds to one decimal only for stalled progress.
Unknown remains Unknown, and tracking loss must not accrue browser-computed time.
Keep the backend observation timestamp visible and mark stale/disconnected data.
No ProgressEvaluator changes are needed.

## Current frontend

A shared Progress context section appears in selected seat/review details.
It explicitly marks evaluated progress, current stall and recent history
unavailable until the above read exists. Matching seat task state is shown only
when session/seat/activity identities match; another task's observation is not
shown as context for an older review. Existing seat realtime updates remain intact.
There is no new endpoint call, speculative column selection, local timer, browser
history accumulator, fake example sequence or frontend evaluation logic.
