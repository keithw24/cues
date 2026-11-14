import type { SeatState } from "@/lib/dashboard";
import type { ReactNode, RefObject } from "react";
import { activityLabel, type TeacherReview } from "@/lib/teacher-reviews";

// One review, as a teacher needs it: who, which task, when, and the decision
// (the actions passed in as children). The model's internals (decision code,
// stall seconds, escalation reason, evidence list) stay out of the way.
// Time of day, plus the date when the review is from an earlier day.
function reviewTime(at: string) {
  const date = new Date(at);
  const today = new Date().toDateString() === date.toDateString();
  return new Intl.DateTimeFormat(undefined, {
    ...(today ? {} : { month: "short", day: "numeric" }),
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function TeacherReviewDetails({
  review,
  seats,
  activities,
  stale,
  close,
  headingRef,
  children,
}: {
  review?: TeacherReview;
  seats: readonly {
    id: string;
    display_name: string;
    state?: SeatState | null;
  }[];
  activities: readonly { id: string; name: string }[];
  stale: boolean;
  close: () => void;
  headingRef: RefObject<HTMLHeadingElement | null>;
  children?: ReactNode;
}) {
  const name = review
    ? (seats.find((seat) => seat.id === review.seat_id)?.display_name ??
      "A student")
    : "Review";
  return (
    <section
      className="review-details"
      aria-labelledby="review-detail-heading"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          close();
        }
      }}
    >
      <header className="panel-heading">
        <h2 id="review-detail-heading" ref={headingRef} tabIndex={-1}>
          {name}
        </h2>
        <button type="button" className="text-button" onClick={close}>
          Back
        </button>
      </header>
      <div className="detail-body">
        {!review ? (
          <p role="status">This review was already answered.</p>
        ) : (
          <>
            <p className="detail-description">
              {activityLabel(
                review.activity_id,
                activities.find((item) => item.id === review.activity_id)?.name,
              )}{" "}
              ·{" "}
              <time dateTime={review.created_at}>
                {reviewTime(review.created_at)}
              </time>
              {review.priority === "elevated" ? " · Urgent" : ""}
            </p>
            {stale ? (
              <p className="detail-description" role="status">
                Reconnecting… this may have changed.
              </p>
            ) : null}
            {children}
          </>
        )}
      </div>
    </section>
  );
}
