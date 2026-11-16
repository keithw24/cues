import type { ReactNode, RefObject } from "react";
import type { SeatView } from "@/lib/dashboard";
import type { ReviewGroup } from "@/lib/teacher-reviews";
import type { observationPresentation } from "@/lib/observation-presentation";
import { ReviewRowContent } from "@/components/workspace-rows";
import { ReviewsUnavailable } from "@/components/dashboard/reviews-unavailable";

type Presentation = ReturnType<typeof observationPresentation>;

type Props = {
  headingRef: RefObject<HTMLHeadingElement | null>;
  groups: ReviewGroup[];
  /** Flagged by the camera, with no request yet. */
  flagged: SeatView[];
  seats: SeatView[];
  inView: SeatView[];
  /** Only name the activity on a row when the class is on more than one. */
  mixedActivities: boolean;
  nameOf: (seatId: string) => string;
  present: (seat: SeatView) => Presentation;
  /** One expandable row (the dashboard owns which row is open). */
  renderRow: (
    seatId: string,
    content: ReactNode,
    presentation: Presentation | null,
    pending: ReviewGroup["reviews"],
  ) => ReactNode;
  waitingCount: number;
  showCount: boolean;
  feedProblem: boolean;
  feedLoading: boolean;
  onRetry: () => void;
  /** What to say when the list is empty and the feed is fine. */
  emptyText: string | null;
};

/** The Attention panel: people Cues asked about, then people the camera flagged. */
export function AttentionList({
  headingRef,
  groups,
  flagged,
  seats,
  inView,
  mixedActivities,
  nameOf,
  present,
  renderRow,
  waitingCount,
  showCount,
  feedProblem,
  feedLoading,
  onRetry,
  emptyText,
}: Props) {
  return (
    <>
      <header className="panel-heading">
        <h2 id="class-heading" ref={headingRef} tabIndex={-1}>
          Attention
        </h2>
        {showCount && waitingCount ? (
          <span className="ws-count">
            {waitingCount}
            <span className="sr-only"> waiting</span>
          </span>
        ) : null}
      </header>

      {feedProblem ? (
        <ReviewsUnavailable loading={feedLoading} onRetry={onRetry} />
      ) : null}

      {groups.length || flagged.length ? (
        <ul className="row-list">
          {groups.map((group) => {
            const seat = seats.find((s) => s.id === group.seat_id);
            const visible = inView.some((s) => s.id === group.seat_id);
            return renderRow(
              group.seat_id,
              <ReviewRowContent
                name={nameOf(group.seat_id)}
                meta={
                  !visible ? "Not in view" : mixedActivities && seat ? seat.activity : ""
                }
                time={group.latest}
                elevated={group.elevated}
              />,
              visible && seat ? present(seat) : null,
              group.reviews,
            );
          })}
          {flagged.map((seat) =>
            renderRow(
              seat.id,
              <ReviewRowContent
                name={seat.display_name}
                meta={
                  mixedActivities
                    ? `${seat.activity} · flagged by the camera`
                    : "Flagged by the camera"
                }
                time={seat.state?.updated_at ?? ""}
                timeLabel="Now"
                elevated={false}
              />,
              present(seat),
              [],
            ),
          )}
        </ul>
      ) : emptyText ? (
        <p className="panel-empty" role="status">
          {emptyText}
        </p>
      ) : null}
    </>
  );
}
