import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { SupabaseClient } from "@supabase/supabase-js";
import {
  INTERVENTION_MENU,
  approveIntervention,
  isInterventionKey,
} from "../lib/interventions.ts";
import {
  REVIEW_COLUMNS,
  REVIEW_COLUMNS_WITH_INTERVENTIONS,
  parseTeacherReviews,
} from "../lib/teacher-reviews.ts";

const ID = "11111111-1111-4111-8111-111111111111";
const SESSION = "22222222-2222-4222-8222-222222222222";
const row = (extra: Record<string, unknown> = {}) => ({
  id: ID,
  session_id: SESSION,
  seat_id: "S1-P1",
  activity_id: "raise_hand",
  created_at: "2026-11-14T12:00:00Z",
  priority: "normal",
  decision: "teacher_review_warranted",
  rationale: "Progress stalled.",
  evidence_used: ["current_progress"],
  status: "pending",
  resolved_at: null,
  ...extra,
});

function rpcClient(response: { data?: unknown; error?: unknown }) {
  const calls: unknown[] = [];
  const client = {
    rpc(name: string, args: unknown) {
      calls.push([name, args]);
      return { abortSignal: async () => ({ data: null, error: null, ...response }) };
    },
  } as unknown as SupabaseClient;
  return { client, calls };
}

test("the menu holds exactly the approved supports, worded as what an adult does", () => {
  assert.equal(Object.keys(INTERVENTION_MENU).length, 6);
  for (const label of Object.values(INTERVENTION_MENU))
    assert.doesNotMatch(label, /anxious|upset|angry|sad|frustrat|diagnos|disorder/i);
  assert.equal(isInterventionKey("offer_break"), true);
  assert.equal(isInterventionKey("change_the_task"), false);
  assert.equal(isInterventionKey("constructor"), false);
  assert.equal(isInterventionKey(null), false);
});

test("a review row reads its suggestion only when it is on the menu", () => {
  const [ok] = parseTeacherReviews([row({ suggested_intervention: "show_example" })]);
  assert.equal(ok.suggested_intervention, "show_example");
  const [off] = parseTeacherReviews([row({ suggested_intervention: "change_the_task" })]);
  assert.equal(off.suggested_intervention, null);
  const [none] = parseTeacherReviews([row({ suggested_intervention: null })]);
  assert.equal(none.suggested_intervention, null);
  // A database without the column: the key is absent and nothing breaks.
  const [old] = parseTeacherReviews([row()]);
  assert.equal("suggested_intervention" in old, false);
});

test("the extra column is requested only with the flag", () => {
  assert.ok(!REVIEW_COLUMNS.includes("suggested_intervention"));
  assert.ok(REVIEW_COLUMNS_WITH_INTERVENTIONS.endsWith(",suggested_intervention"));
  const feed = readFileSync(new URL("../lib/teacher-review-feed.ts", import.meta.url), "utf8");
  assert.match(feed, /interventions \? REVIEW_COLUMNS_WITH_INTERVENTIONS : REVIEW_COLUMNS/);
});

test("approving calls the RPC with the review and the chosen support", async () => {
  const { client, calls } = rpcClient({ data: { review_id: ID, action: "offer_break" } });
  assert.equal(await approveIntervention(client, ID, "offer_break"), "offer_break");
  assert.deepEqual(calls, [["approve_review_intervention", { review_id: ID, action: "offer_break" }]]);
});

test("a refusal or a mismatched answer is never shown as approved", async () => {
  const failing = rpcClient({ error: { message: "review is closed" } });
  await assert.rejects(approveIntervention(failing.client, ID, "offer_break"), /Could not save/);
  const wrong = rpcClient({ data: { review_id: ID, action: "model_task" } });
  await assert.rejects(approveIntervention(wrong.client, ID, "offer_break"), /Could not save/);
  const empty = rpcClient({ data: null });
  await assert.rejects(approveIntervention(empty.client, ID, "offer_break"), /Could not save/);
});

test("an action outside the menu is refused before any request", async () => {
  const { client, calls } = rpcClient({});
  await assert.rejects(
    approveIntervention(client, ID, "change_the_task" as never),
    /Choose a support/,
  );
  assert.equal(calls.length, 0);
});

test("the suggestion shows only with web.interventions, and approving confirms the review", () => {
  const source = readFileSync(
    new URL("../components/teacher-review-actions.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /interventionsEnabled \? \(/);
  assert.match(source, /status: "confirmed"/);
  const page = readFileSync(new URL("../app/dashboard/page.tsx", import.meta.url), "utf8");
  assert.match(page, /isEnabled\("web\.interventions"\)/);
});
