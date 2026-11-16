import { useState } from "react";
import type { SeatView } from "@/lib/dashboard";
import { unexplainedDrops } from "@/lib/classroom-view";

type Inputs = {
  /** Flagged people with no request yet, and how many people are waiting in all. */
  flaggedOnly: SeatView[];
  waitingCount: number;
  markedSeats: ReadonlySet<string>;
  /** People who already have a request. */
  askedSeatIds: string[];
  seats: SeatView[];
  observationNow: number | null;
  reviewsLive: boolean;
  hasSnapshot: boolean;
};

/** The count the Cues companion follows (null while it should rest), and a way to forget
 * everyone who was just lost from view, for when the whole class starts over. */
export function useCompanionCount({
  flaggedOnly,
  waitingCount,
  markedSeats,
  askedSeatIds,
  seats,
  observationNow,
  reviewsLive,
  hasSnapshot,
}: Inputs) {
  // What the companion follows. With flagged people counted, wait for the
  // camera data too, so a count that is about to grow never reads as cleared.
  // A flagged person who drops out of the count only because the camera lost
  // them or went quiet (not a mark, a request or a reset) makes the companion
  // rest until they are back or resolved: that is not a cleared queue.
  const flaggedIds = flaggedOnly.map((seat) => seat.id).join(",");
  const [countedFlagged, setCountedFlagged] = useState(flaggedIds);
  const [droppedFlagged, setDroppedFlagged] = useState<readonly string[]>([]);
  const nowFlagged = new Set(flaggedIds ? flaggedIds.split(",") : []);
  const dropReasons = {
    marked: markedSeats,
    asked: new Set(askedSeatIds),
    row: (id: string) => seats.find((seat) => seat.id === id)?.state ?? undefined,
    clock: observationNow,
  };
  if (flaggedIds !== countedFlagged) {
    setCountedFlagged(flaggedIds);
    setDroppedFlagged((previous) =>
      unexplainedDrops(
        [
          ...new Set([
            ...previous,
            ...(countedFlagged ? countedFlagged.split(",") : []),
          ]),
        ],
        nowFlagged,
        dropReasons,
      ),
    );
  }
  const unexplained = unexplainedDrops(droppedFlagged, nowFlagged, dropReasons);
  // Forget anyone who has since been resolved (or timed out), so a later loss
  // of someone no longer flagged never makes the companion rest.
  if (
    flaggedIds === countedFlagged &&
    unexplained.length !== droppedFlagged.length
  )
    setDroppedFlagged(unexplained);
  const companionCount =
    reviewsLive &&
    ((hasSnapshot && unexplained.length === 0))
      ? waitingCount
      : null;
  const forgetLostPeople = () => setDroppedFlagged([]);
  return { companionCount, forgetLostPeople };
}
