import assert from "node:assert/strict";
import test from "node:test";
import {
  groupReviewsBySeat,
  pendingReviews,
  type TeacherReview,
} from "../lib/teacher-reviews.ts";

const review = (
  id: string,
  seat_id: string,
  created_at: string,
  priority: "normal" | "elevated" = "normal",
): TeacherReview => ({
  id,
  session_id: "00000000-0000-4000-8000-000000000001",
  seat_id,
  activity_id: "raise_hand",
  created_at,
  priority,
  rationale: "Progress has stalled.",
  evidence_used: [],
  status: "pending",
  resolved_at: null,
});

test("reviews for the same person collapse into one group in queue order", () => {
  const queue = pendingReviews([
    review("a", "S1-P2", "2026-11-14T12:39:00Z"),
    review("b", "S1-P1", "2026-11-14T12:26:00Z", "elevated"),
    review("c", "S1-P2", "2026-11-14T12:41:00Z", "elevated"),
    review("d", "S1-P1", "2026-11-14T12:36:00Z"),
  ]);
  const groups = groupReviewsBySeat(queue);
  assert.deepEqual(
    groups.map((g) => [g.seat_id, g.reviews.map((r) => r.id)]),
    [
      ["S1-P1", ["b", "d"]],
      ["S1-P2", ["c", "a"]],
    ],
  );
  assert.equal(groups[0].elevated, true);
  assert.equal(groups[1].latest, "2026-11-14T12:41:00Z");
});

test("a person with only normal reviews is not flagged", () => {
  const [group] = groupReviewsBySeat([
    review("a", "S1-P3", "2026-11-14T12:00:00Z"),
  ]);
  assert.equal(group.elevated, false);
  assert.equal(group.reviews.length, 1);
});
