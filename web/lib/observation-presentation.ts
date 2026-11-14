import { statuses, type SeatState } from "./dashboard.ts";

export const OBSERVATION_STALE_MS = 5000;
export type ObservationOptions = {
  enabled: boolean;
  now: number | null;
  connected: boolean;
};
/** Display freshness only. Never changes task/review state or calculates stalled_seconds. */
export function observationPresentation(
  state: SeatState | null,
  options?: ObservationOptions,
) {
  const empty = {
    label: "Awaiting observation",
    detail: "No observation has been received.",
    score: null,
    currentStatus: null,
    needsReview: false,
    unavailable: true,
  };
  if (!state) return empty;
  const hidden = (label: string, detail: string) => ({
    ...empty,
    label,
    detail,
  });
  if (options?.enabled) {
    const observedAt = Date.parse(state.updated_at);
    if (
      !options.connected ||
      options.now === null ||
      !Number.isFinite(observedAt) ||
      observedAt > options.now ||
      options.now - observedAt >= OBSERVATION_STALE_MS
    )
      return hidden(
        "Updates paused",
        "No fresh observation is available. The last observation is shown below.",
      );
    if (state.status === "tracking_lost")
      return hidden(
        "Tracking lost",
        "This position is no longer being tracked. This is not a failed attempt.",
      );
    if (state.tracking_valid === false)
      return hidden(
        "Tracking unavailable",
        "Tracking is unavailable for this observation. This is not a failed attempt.",
      );
    if (state.tracking_valid !== true)
      return hidden(
        "Tracking unknown",
        "Tracking validity has not been provided for this observation.",
      );
  }
  return {
    label: statuses[state.status].label,
    detail: statuses[state.status].detail,
    score: state.status === "tracking_lost" ? null : state.task_score,
    currentStatus: state.status,
    needsReview: state.status === "review" || state.status === "needs_help",
    unavailable: state.status === "tracking_lost",
  };
}
