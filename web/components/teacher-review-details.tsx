import type { ObservationOptions } from "@/lib/observation-presentation";
import { ProgressContext } from "@/components/progress-context";
import type { SeatState } from "@/lib/dashboard";
import type { ReactNode, RefObject } from "react";
import {
  activityLabel,
  decisionLabels,
  evidenceLabels,
  priorityLabels,
  teacherRationale,
  type TeacherReview,
} from "@/lib/teacher-reviews";

export function TeacherReviewDetails({
  review,
  observationOptions,
  seats,
  activities,
  stale,
  close,
  headingRef,
  children,
}: {
  observationOptions?: ObservationOptions;
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
          Review details
        </h2>
        <button type="button" className="text-button" onClick={close}>
          Back to queue
        </button>
      </header>
      <div className="detail-body">
        {!review ? (
          <p role="status">
            This review is no longer in the pending queue. It may have been
            resolved or removed.
          </p>
        ) : (
          <>
            {stale ? (
              <p className="detail-description" role="status">
                Showing the last loaded assessment. Return to the queue to
                reconnect.
              </p>
            ) : null}
            <dl className="detail-facts">
              <div>
                <dt>Decision</dt>
                <dd>
                  {review.decision
                    ? decisionLabels[review.decision]
                    : "Decision unavailable"}
                </dd>
              </div>
              <div>
                <dt>Priority</dt>
                <dd>{priorityLabels[review.priority]}</dd>
              </div>
              <div>
                <dt>Seat</dt>
                <dd>
                  {seats.find((seat) => seat.id === review.seat_id)
                    ?.display_name ?? `Seat ${review.seat_id}`}
                </dd>
              </div>
              <div>
                <dt>Activity</dt>
                <dd>
                  {activityLabel(
                    review.activity_id,
                    activities.find((item) => item.id === review.activity_id)
                      ?.name,
                  )}
                </dd>
              </div>
              <div>
                <dt>Created</dt>
                <dd>
                  <time dateTime={review.created_at}>
                    {new Intl.DateTimeFormat(undefined, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(review.created_at))}
                  </time>
                </dd>
              </div>
            </dl>
            <section className="detail-section">
              <h3>Agent rationale</h3>
              <p>{teacherRationale(review.rationale)}</p>
            </section>
            <section className="detail-section">
              <h3>Evidence used</h3>
              {review.evidence_used.length ? (
                <ul className="review-evidence-list">
                  {review.evidence_used.map((source) => (
                    <li key={source}>{evidenceLabels[source]}</li>
                  ))}
                </ul>
              ) : (
                <p>No evidence summary provided.</p>
              )}
            </section>
            <ProgressContext
              observation={
                seats.find((seat) => seat.id === review.seat_id)?.state
              }
              scope={review}
              observationOptions={observationOptions}
            />
            {children}
          </>
        )}
      </div>
    </section>
  );
}
