import { type SeatState } from "@/lib/dashboard";
import {
  observationPresentation,
  type ObservationOptions,
} from "@/lib/observation-presentation";
import { matchingTaskObservation, evaluatedProgress } from "@/lib/progress-context";

/** Display backend evaluations only; never calculate progress from browser score/time. */
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
  const progress = evaluatedProgress(matched, observationOptions?.now ?? undefined);
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
          <dd>{progress?.trend ?? "Unavailable"}</dd>
        </div>
        <div>
          <dt>Current stall</dt>
          <dd>{progress ? `${progress.stalled_seconds.toFixed(1)} seconds` : "Unavailable"}</dd>
        </div>
      </dl>
      <p>Recent progress: {progress?.recent.map(entry => entry.progress.trend).join(" → ") || "No fresh evaluated history available."}</p>
      <p className="progress-source-note">
        {progress ? "Live backend evaluation. Tracking gaps never count as failure." :
          "Waiting for fresh backend evaluation for this task revision."}
      </p>
    </section>
  );
}
