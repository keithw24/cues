import type { SeatStatus, SeatView } from "./dashboard.ts";
import { resolutionLabels } from "./teacher-reviews.ts";
import {
  inCameraView,
  observationPresentation,
  type ObservationOptions,
} from "./observation-presentation.ts";

/** How the Live screen (/live) turns seats, reviews and the teacher's
 * decisions into the class list and its counts. Pure, so it is tested
 * without rendering. Everything is keyed by seat or review id, never by a
 * display name. */
export type LiveStatus =
  "finished" | "needs" | "working" | "ready" | "checking" | "quiet";
export type LivePerson = {
  id: string;
  name: string;
  status: LiveStatus;
  label: string;
  details: string[];
};
export type LiveDecision = {
  reviewId: string;
  seatId: string;
  decision: "confirmed" | "dismissed";
  saved: boolean;
  at: number;
  /** The seat's task status when the teacher decided. */
  statusAtDecision: SeatStatus | null;
};

/** The status shown for one seat. Live state wins: a finished seat shows as
 * finished, and a pending review shows as waiting. A teacher's "Support
 * needed" marker lasts only until the camera reports a different status. */
export function liveStatus(
  seat: SeatView,
  options: ObservationOptions,
  pendingReviewSeats: ReadonlySet<string>,
  decision?: LiveDecision,
): [LiveStatus, string] {
  const presentation = observationPresentation(seat.state, options);
  if (pendingReviewSeats.has(seat.id)) return ["needs", "Review waiting"];
  if (presentation.currentStatus === "done") return ["finished", "Finished"];
  if (
    decision?.decision === "confirmed" &&
    (seat.state?.status ?? null) === decision.statusAtDecision
  )
    return ["checking", resolutionLabels.confirmed];
  if (presentation.needsReview) return ["needs", "Needs you"];
  if (presentation.currentStatus === "in_progress")
    return ["working", presentation.label];
  if (presentation.currentStatus === "idle") return ["ready", "Ready"];
  return ["quiet", presentation.label];
}

/** The people the camera sees now, left to right, with their status. */
export function livePeople(
  seats: readonly SeatView[],
  options: ObservationOptions,
  pendingReviewSeats: ReadonlySet<string>,
  decisions: readonly LiveDecision[],
): LivePerson[] {
  return seats
    .filter((seat) => inCameraView(seat.state, options))
    .map((seat, index) => {
      const decision = decisions.findLast((item) => item.seatId === seat.id);
      const [status, label] = liveStatus(
        seat,
        options,
        pendingReviewSeats,
        decision,
      );
      return {
        id: seat.id,
        name: seat.display_name,
        status,
        label,
        details: [
          observationPresentation(seat.state, options).detail,
          `${seat.activity} · position ${index + 1} from the left`,
        ],
      };
    });
}

/** The headline counts for the class list. */
export function liveCounts(people: readonly { status: LiveStatus }[]) {
  return {
    finished: people.filter((p) => p.status === "finished").length,
    working: people.filter(
      (p) => p.status === "working" || p.status === "checking",
    ).length,
    total: people.length,
  };
}

/** How many seats are waiting on the teacher, counted by seat id. */
export function waitingCount(
  reviewSeatIds: readonly string[],
  flaggedSeatIds: readonly string[],
): number {
  return new Set([...reviewSeatIds, ...flaggedSeatIds]).size;
}
