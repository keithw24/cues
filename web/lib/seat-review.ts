import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * "Mark as reviewed": the teacher has checked in with a flagged child.
 *
 * The database function (mark_seat_reviewed) closes that child's open review requests
 * and records a mark. Vision reads the mark to put the child back to working and restart
 * the no-progress timer; the agent restarts its stall detection. The browser names only
 * the session and the person: who the teacher is and which station they may act on come
 * from the sign-in, never from here.
 */
export type SeatReviewResult = { closed: number };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SEAT_ID = /^[A-Za-z0-9_-]{1,64}$/;

export const MARK_REVIEWED_ERRORS = {
  signIn: "Sign in as a teacher of this station to mark someone as reviewed.",
  gone: "This session has ended, or this person is no longer in it. Refresh and try again.",
  failed: "Could not mark as reviewed. Check your connection and try again.",
} as const;

export function parseSeatReview(data: unknown): SeatReviewResult {
  const row = data as { closed?: unknown; marked_at?: unknown } | null;
  if (
    !row ||
    typeof row !== "object" ||
    typeof row.closed !== "number" ||
    !Number.isInteger(row.closed) ||
    row.closed < 0 ||
    typeof row.marked_at !== "string" ||
    !Number.isFinite(Date.parse(row.marked_at))
  )
    throw new Error("Invalid response");
  return { closed: row.closed };
}

export async function markSeatReviewed(
  client: SupabaseClient,
  sessionId: string,
  seatId: string,
): Promise<SeatReviewResult> {
  if (!UUID.test(sessionId) || !SEAT_ID.test(seatId))
    throw new Error(MARK_REVIEWED_ERRORS.gone);
  let response;
  try {
    response = await client
      .rpc("mark_seat_reviewed", { p_session_id: sessionId, p_seat_id: seatId })
      .abortSignal(AbortSignal.timeout(12000));
  } catch {
    throw new Error(MARK_REVIEWED_ERRORS.failed);
  }
  if (response.error?.code === "42501") throw new Error(MARK_REVIEWED_ERRORS.signIn);
  if (response.error?.code === "22023") throw new Error(MARK_REVIEWED_ERRORS.gone);
  if (response.error) throw new Error(MARK_REVIEWED_ERRORS.failed);
  try {
    return parseSeatReview(response.data);
  } catch {
    throw new Error(MARK_REVIEWED_ERRORS.failed);
  }
}
