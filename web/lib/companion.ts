/** What the Cues companion on the To review pill does when the waiting count
 * changes. Pure, so it is tested without rendering. */

export type CompanionPhase = "rest" | "waiting" | "eating" | "done";

/** Blue at rest, orange while something waits (and while eating), green when
 * the queue has just been cleared. */
export const COMPANION_COLORS = {
  rest: "#5763d2",
  waiting: "#e8741f",
  eating: "#e8741f",
  done: "#34a46a",
} as const satisfies Record<CompanionPhase, `#${string}`>;

/** The chomp runs this long; then it stays green this long before resting. */
export const EAT_MS = 1800;
export const DONE_MS = 2200;

export type CompanionStep =
  /** The review feed is not live (dropped, reconnecting, loading): rest
   * quietly; never treat it as a cleared queue. */
  | { kind: "rest" }
  /** The feed came back: show the queue as it is, without a hop or an eat. */
  | { kind: "sync" }
  /** More waiting than before: turn orange and hop. */
  | { kind: "hop" }
  /** The queue just cleared: eat this many, then go green, then rest. */
  | { kind: "eat"; eaten: number }
  /** Fewer, but not zero (or no change): stay as it is. */
  | { kind: "none" };

/** `null` means the review feed is not live, so the count is unknown. */
export function companionStep(
  before: number | null,
  count: number | null,
): CompanionStep {
  if (count === null) return { kind: "rest" };
  if (before === null) return { kind: "sync" };
  if (count > before) return { kind: "hop" };
  if (count === 0 && before > 0) return { kind: "eat", eaten: before };
  return { kind: "none" };
}

/** Where the companion starts when the page loads. */
export function initialCompanionPhase(count: number | null): CompanionPhase {
  return count !== null && count > 0 ? "waiting" : "rest";
}
