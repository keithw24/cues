import type { SeatState } from "./dashboard.ts";

/** Seat observations are not evaluated ProgressState or a progress history. */
export function matchingTaskObservation(
  observation: SeatState | null | undefined,
  scope: { session_id: string; seat_id: string; activity_id: string | null },
): SeatState | null {
  if (
    !observation ||
    observation.session_id !== scope.session_id ||
    observation.seat_id !== scope.seat_id ||
    observation.activity_id !== scope.activity_id
  )
    return null;
  return observation;
}
