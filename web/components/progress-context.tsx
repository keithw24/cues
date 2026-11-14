import { type SeatState } from "@/lib/dashboard";
import {
  observationPresentation,
  type ObservationOptions,
} from "@/lib/observation-presentation";
import { matchingTaskObservation } from "@/lib/progress-context";

/** The evaluator/history are not exposed yet. Never calculate progress from scores or elapsed browser time. */
export function ProgressContext({
  observation,
  scope,
  observationOptions,
}: {
  observationOptions?: ObservationOptions;
  observation?: SeatState | null;
  scope?: { session_id: string; seat_id: string; activity_id: string | null };
}) {
  const matched = scope ? matchingTaskObservation(observation, scope) : null;
  return (
    <section
      className="detail-section progress-context"
      aria-label="Progress context"
    >
      <h3>Progress context</h3>
      <dl className="detail-facts">
        <div>
          <dt>Task state</dt>
          <dd>
            {matched
              ? observationPresentation(matched, observationOptions).label
              : "Unavailable"}
          </dd>
        </div>
        <div>
          <dt>Evaluated progress</dt>
          <dd>Unavailable</dd>
        </div>
        <div>
          <dt>Current stall</dt>
          <dd>Unavailable</dd>
        </div>
      </dl>
      <p>Recent progress: history is not available yet.</p>
      <p className="progress-source-note">
        Evaluated progress and stall duration have not been shared by the
        backend.
      </p>
    </section>
  );
}
