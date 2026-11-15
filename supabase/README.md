# Cues database

## Reconciled migration history

On November 14, 2026 the local chain was made unique without changing SQL:
session_controls moved from 20261114000300 to 20261114000310;
person_observations moved from 20261114000400 to 20261114000510;
station_session_sync moved from 20261114000500 to 20261114000520.
This orders the unconditional tracking_valid addition before person observations'
IF NOT EXISTS addition. All eleven migrations passed fresh local PostgreSQL replay
with minimal Supabase Auth stubs; this is SQL replay, not full Auth/Realtime emulation.

Hosted effects through 007 were audited before repair. Official Supabase CLI
3.1.0 migration repair marked the ten predecessors applied without replaying SQL.
The official list now matches through 007; 008 remains pending. Dry-run selected
only 20261114000800_station_pairing.sql, with no seed or role execution.
No application schema was deployed during reconciliation.

No project dependency installation is needed for the pinned CLI. The repo-local
config is supabase/config.toml. The helper below loads the saved database URL,
validates it identifies the configured Supabase project and redacts credentials.
It invokes only official CLI commands, never direct migration-ledger SQL:

```bash
uv run python scripts/supabase-migrations.py list
uv run python scripts/supabase-migrations.py dry-run
```

The helper's repair-history action was used once for the verified predecessors;
do not use it to mark future changes applied without executing them.
For a separately authorized real deployment, load DATABASE_URL securely into the
shell and use the same explicit target (CLI 3 uses --remote=<database URL>):

```bash
npx --yes supabase@3.1.0 db push --remote="$DATABASE_URL" --dry-run --skip-vault
# Only after reviewing the pending list and authorizing deployment:
npx --yes supabase@3.1.0 db push --remote="$DATABASE_URL" --skip-vault
```

Never print the connection URL, enable shell tracing, or run a remote db reset.
The earlier duplicate-history warnings in historical notes are superseded by
this reconciliation. Fresh projects should apply the current unique sorted chain.

## Mark as reviewed (migration 015, local only)

`20261114001500_review_marks.sql`:

- **`mark_seat_reviewed(session, seat)`** (signed-in teachers of the station only; the
  browser names just the session and the person). It records a mark in
  `seat_review_marks` and closes that person's open review requests as `reviewed`.
  Vision reads the mark to put the child back to working and restart the no-progress
  timer (flag `vision.review_marks`); the agent reads it to restart stall detection.
  Marking works even when the child has no open review.
- **Completing the task closes the review request.** A trigger on `seat_state` closes
  that person's open reviews for the activity as `expired` when the status becomes `done`.
- `reviewed` is a new review status (a teacher marked the child reviewed); like `expired`
  it is not a decision on the review. A one-time cleanup closes open reviews of children
  who have already completed their task.
- The dashboard button is under the existing `web.teacher_review_actions` flag.

Local tests: `supabase/tests/test_review_marks.py`. Not deployed.

## Review lifecycle (migration 013, local only)

`20261114001300_review_lifecycle.sql`:

- **Reviews close with their session.** When a session's `ended_at` is set, its pending
  reviews become `expired` (a trigger, so it covers every way a session can end). A review
  that arrives after its session ended is closed on arrival. `expired` is not `dismissed`:
  the dashboard shows dismissed as the teacher's own "No support needed", and nobody decided
  that. Teachers still resolve reviews only as confirmed or dismissed
  (`resolve_teacher_review` is unchanged); `expired` cannot be reopened or changed.
- **One open review per person.** A partial unique index allows one pending review per
  session, seat and activity. The agent reuses the open one for later evaluations (no new
  row, no second notification) and opens a new one only after it is resolved.
- **One-time cleanup when applied:** pending reviews in sessions that already ended become
  `expired`, and in running sessions the newer duplicates of an open review become `expired`
  (the oldest stays open). Teachers' own confirmed/dismissed decisions are never changed.

Local tests: `supabase/tests/test_review_lifecycle.py` (needs PostgreSQL, see below).
Not deployed.

## Default station per teacher (migration 011, local only)

`20261114001100_default_station.sql` adds `station_teachers.is_default` (at most one
default per teacher, enforced by a partial unique index) and
`get_or_create_my_default_station()`, callable only by signed-in users and always for
`auth.uid()`. A teacher whose single existing assignment is a station keeps it as their
default (backfilled; Keith → S1). A teacher with none gets a new `S<n>` station with
simulated `S<n>-P1..P4` person slots. Existing stations, sessions and their owners are
not modified. Nothing here has been deployed.

Local tests (need PostgreSQL's `initdb`, `pg_ctl` and `psql`; skipped otherwise):
`uv run pytest supabase/tests/test_default_station.py supabase/tests/test_migration_replay.py`.

## Station pairing (migration 008, local only)

`20261114000800_station_pairing.sql` adds private, single-use station invitations.
Apply through the reviewed migration sequence; the duplicate history is now
reconciled as described above. A verified push will apply pending migrations only.
Nothing in this pairing implementation has been deployed by this change.

Trusted operator SQL (database owner, or a backend service-role client):

```sql
select * from public.issue_station_pairing_code('S1', 600);
```

Returns a random UUID-format code and expires_at once. Only its normalized
SHA-256 hash is stored. The default lifetime is ten minutes, capped at one hour.
Display/share the code privately; do not put it in application logs. Reissuing
creates another independently valid code; it does not revoke earlier codes.
Service-role operators can invalidate an unused code by deleting its row.

Authenticated frontend contract:

```ts
const { data, error } = await supabase.rpc('redeem_station_pairing_code', {
  code: enteredCode,
});
// data: [{ station_id: 'S1' }]; refresh existing station/session controls afterward.
```

The browser supplies only the code. Case, hyphens and whitespace are normalized.
The server locks the code, checks expiry/unused state, inserts membership for
auth.uid(), and consumes the code atomically. Existing membership is retained
without duplication; the valid code is still consumed. No session is created or
claimed. Existing require_station_teacher and start_station_activity remain intact.

No browser access to code rows or issuance is granted. Redemption is available
only to authenticated callers. Service-role table access/issuance is preserved.
High-entropy generated codes resist guessing; no low-entropy numeric-code flow or
public issuance endpoint is provided. Photon registration and onboarding UI remain
separate work.

Local SQL/race checks (requires already-installed initdb, pg_ctl, psql):

```bash
uv run pytest supabase/tests/test_station_pairing.py -q
```

These tests start/remove a temporary local PostgreSQL cluster and never read
DATABASE_URL or contact hosted Supabase. They validate migration 008 against a
minimal station/Auth prerequisite schema, not a replay of all historical migrations.

`migrations/20261114000100_initial_schema.sql` implements PRD §17.3 without changing
the shared table/event fields. Apply it once in a new Supabase project's SQL
Editor, apply subsequent migrations in filename order, then run `seed.sql`. The seed uses only simulated data and can be rerun
without resetting existing rows. Do not reapply the migration to an existing schema.

The initial nine tables have Row Level Security enabled. The publishable key can read
simulated seats and their associated station, session, activity and seat state.
These demo rows are publicly readable: use no real student data or private notes
in them. Browser writes are denied. Events, alerts, interventions and support
preferences are server-only. The authenticated resolution RPC exists; teacher login/profile UI and session ownership authorization remain gaps.

`seat_state` is included in the `supabase_realtime` publication. The frontend must
fetch initial state and subscribe to Postgres Changes; the current dashboard implements initial state reads and subscriptions.

Migration `20261114000500_add_seat_state_tracking_valid.sql` adds nullable
`seat_state.tracking_valid` without a default. Apply it after migration 004.
Leaving the column nullable preserves unknown historical observations instead of
marking them valid. Applied to and verified against the hosted project on
November 14, 2026. A live upsert/read through the vision Supabase sink confirmed
both valid tracking and tracking loss, including a null `task_score` during loss.

Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` in
`web/.env.local`. Privileged clients use the root `.env` with `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY` (as consumed by the current vision client). Never put
a service-role or secret key in browser variables. Vision cloud event writes also
require the `vision.supabase_events` flag; enable it for the live demo after configuring the backend credentials.

In the SQL Editor, verify tables, RLS, demo rows and publication membership:

```sql
select tablename, rowsecurity from pg_tables where schemaname = 'public' order by tablename;
select * from public.seat_state;
select tablename from pg_publication_tables where pubname = 'supabase_realtime';
begin;
set local role anon;
select * from public.seats;
select * from public.seat_state;
rollback;
```

Once a dashboard subscribes, update a simulated seat through the Table Editor
and verify that its card changes without refreshing. Camera, model, agent,
teacher approval and Photon verification are separate integration work.

Verified against the hosted `cues` project on November 13, 2026:

- All nine tables have RLS enabled.
- The configured publishable key read simulated seat/state fixtures and the
  associated station, activity and session. Seeded status is `idle`, matching
  the existing vision status vocabulary.
- Anonymous INSERT/UPDATE privileges on `seat_state` are absent; reading alerts
  through the publishable key is denied.
- A Postgres Changes subscription using the publishable key received a real
  `seat_state` UPDATE after changing a simulated row's timestamp in the SQL Editor.

The database verification above predates the teacher dashboard implementation.
The dashboard now reads simulated state when `web.dashboard` is enabled; see
`../web/README.md` for app setup and its separate acceptance checks.

## Authenticated resolution RPC

Migration 004 adds `resolve_teacher_review(review_id uuid, action text)` returning
one teacher_reviews row as an array. Actions are confirmed/dismissed; timestamps
are generated by the database. Applied and hosted-tested November 14, 2026.
Only authenticated Auth users may execute it, and only for simulated-seat reviews.
There is no session-owner relationship yet: any authenticated user may resolve
demo reviews. This must be replaced by session authorization before classroom use.
Direct browser writes remain denied. SQL smoke: supabase/tests/resolve_teacher_review.sql.
See notes/michelle.md for non-service authenticated RPC and Realtime verification.

## Teacher reviews

Apply `migrations/20261114000300_teacher_reviews.sql` after the first two migrations
using the Supabase SQL Editor (or `supabase db push` for a linked CLI project).
This adds `public.teacher_reviews`, its indexes, RLS and lifecycle trigger, and
membership in `supabase_realtime`. Applied and verified on the hosted `cues`
project on November 14, 2026; do not reapply it there. See
`../notes/michelle.md` for the hosted verification results.

The table persists the existing Python `TeacherReview`: UUID, creation time,
session/seat/activity, priority, complete evaluation JSON, assessment decision,
rationale, structured evidence labels, status, and resolution time. Only status
and resolved_at may change, and only once from pending to confirmed or dismissed.
The database guard applies to service-role updates too. An identical evaluation
is unique across backend instances; duplicate inserts do not rewrite an assessment
or reopen a resolved review.

The backend composition point is `agent.runtime.create_runtime_agent(model, history)`.
It uses the shared server client factory and injects SupabaseTeacherReviewStore
when SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are configured. Nonempty process
values win over root .env, with web/.env.local as a local fallback; that file's
NEXT_PUBLIC_SUPABASE_URL may supply the URL alongside the server-only key. No new
credentials are needed. Startup checks table access and fails on partial/broken
persistence configuration. Write failures never silently fall back to memory.
The core agent factory remains in-memory by default for direct unit/offline use;
the runtime exposes offline=True, and the live Groq runner has --offline-reviews.
The continuous agent.worker polls seat_state through create_seat_state_runtime.
FastAPI serves vision/video; there is no agent API server. See ../STARTUP.md.

Optional runtime/action smoke (scripted model, real Supabase, isolated probe cleanup):

```bash
uv run python -m agent.hosted_review_smoke
```

This passed against the hosted project on November 14, 2026. Normal unit tests
remain network-independent. Details are in `../notes/michelle.md`.

Evan can fetch initial rows and subscribe to INSERT/UPDATE Postgres Changes on
`public.teacher_reviews`. Existing demo RLS permits read access only where the
matching `seats` row has is_simulated=true. A review with an unknown seat ID remains
server-only until that simulated seat is provisioned. Demo rationale/evidence are
publicly readable: use synthetic data only. There is no frontend subscription in
this change. See [Supabase Postgres Changes](https://supabase.com/docs/guides/realtime/postgres-changes)
for publication and subscriber read-permission requirements.

Anon/authenticated clients receive no direct INSERT/UPDATE/DELETE privileges.
Authenticated users may call resolve_teacher_review for simulated-seat reviews;
anonymous callers cannot. Never send a service-role key to the frontend. Teacher identity/authorization and real classroom
read policies remain future work; do not broaden the demo policy for deployment.

Optional SQL smoke, after applying migrations, with a database-owner connection:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/teacher_reviews.sql
```

This creates synthetic fixtures inside a transaction and rolls them back. It
checks demo RLS, denied anonymous writes, immutable trusted fields, both resolution
statuses, rejected re-resolution, and Realtime publication membership. Validated
locally on PostgreSQL 14 and against the hosted project. A public-key subscription
received real INSERT/pending and UPDATE/confirmed or dismissed events; the
isolated synthetic API probe rows were removed afterward.

## Session ownership on start (migration 007)

Migration 006 adds `sessions.teacher_id` and makes `teacher_reviews` readable only for
sessions the signed-in teacher owns, but `start_station_activity` still created sessions
without an owner. Migration `20261114000700_session_owner_on_start.sql` sets
`teacher_id = auth.uid()` when the RPC creates a session; activity changes keep the
existing owner, and historical sessions stay unowned. The browser never sends a teacher
ID; it only checks that a new session came back owned by the signed-in user. Apply it
after 006. Not applied to the hosted project. SQL smoke (rolls back):
`supabase/tests/session_owner_on_start.sql`, not yet run (no local Postgres).
