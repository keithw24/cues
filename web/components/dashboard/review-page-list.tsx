import type { ReactNode } from "react";
import type { SeatView } from "@/lib/dashboard";
import { reviewIssueLine } from "@/lib/classroom-view";
import type { ReviewGroup } from "@/lib/teacher-reviews";
import { ReviewCard, WaitingReviewCard } from "@/components/review-card";
import { ReviewsUnavailable } from "@/components/dashboard/reviews-unavailable";

type Props = {
  groups: ReviewGroup[];
  /** Flagged by the camera, with no request yet. */
  flagged: SeatView[];
  inView: SeatView[];
  nameOf: (seatId: string) => string;
  activityName: (activityId: string) => string;
  /** The teacher's decision buttons for a group's lead review, or null. */
  decisions: (lead: ReviewGroup["reviews"][number]) => ReactNode;
  flagDecisions: (sessionId: string | null, seatId: string) => ReactNode;
  feedProblem: boolean;
  feedLoading: boolean;
  onRetry: () => void;
  /** What to say when the list is empty and the feed is fine. */
  emptyText: string | null;
};

/** The To review page: one card per person Cues asked about, then people the camera flagged. */
export function ReviewPageList({
  groups,
  flagged,
  inView,
  nameOf,
  activityName,
  decisions,
  flagDecisions,
  feedProblem,
  feedLoading,
  onRetry,
  emptyText,
}: Props) {
  return (
    <section className="review-page" aria-label="To review">
      {feedProblem ? (
        <ReviewsUnavailable loading={feedLoading} onRetry={onRetry} />
      ) : null}
      {groups.length || flagged.length ? (
        <ol className="review-list">
          {groups.map((group, index) => {
            const lead = group.reviews[0];
            const visible = inView.some((seat) => seat.id === group.seat_id);
            return (
              <ReviewCard
                key={group.seat_id}
                headingId={`review-card-${group.seat_id}`}
                index={index + 1}
                name={nameOf(group.seat_id)}
                issue={reviewIssueLine(
                  activityName(lead.activity_id),
                  visible,
                  group.reviews.length,
                )}
                review={lead}
                elevated={group.elevated}
                decisions={decisions(lead)}
              />
            );
          })}
          {flagged.map((seat, index) => (
            <WaitingReviewCard
              key={seat.id}
              headingId={`review-card-${seat.id}`}
              index={groups.length + index + 1}
              name={seat.display_name}
              issue={reviewIssueLine(seat.activity, true, 1)}
              mark={flagDecisions(seat.state?.session_id ?? null, seat.id)}
            />
          ))}
        </ol>
      ) : emptyText ? (
        <p className="list-clear review-clear" role="status">
          {emptyText}
        </p>
      ) : null}
    </section>
  );
}
