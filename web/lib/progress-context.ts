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


export type EvaluatedProgress = {
  trend: "improving" | "stalled" | "completed" | "unknown";
  stalled_seconds: number;
  observed_at: string;
  recent: {observed_at: string; progress: {trend: string; stalled_seconds: number}}[];
};
/** Only backend output for this task revision and a recent observation is displayable. */
export function evaluatedProgress(observation: SeatState | null | undefined,
  now: number = Date.now()): EvaluatedProgress | null {
  if (!observation || observation.tracking_valid !== true || observation.status === "tracking_lost") return null;
  const raw = observation.evaluated_progress;
  if (!raw || typeof raw !== "object") return null;
  const p = raw as Record<string, unknown>;
  const trends = ["improving", "stalled", "completed", "unknown"];
  if (p.session_id !== observation.session_id || p.activity_id !== observation.activity_id ||
      p.session_revision !== observation.session_revision || !trends.includes(String(p.trend)) ||
      typeof p.stalled_seconds !== "number" || !Number.isFinite(p.stalled_seconds) || p.stalled_seconds < 0 ||
      typeof p.observed_at !== "string" || !Number.isFinite(Date.parse(p.observed_at)) ||
      Date.parse(p.observed_at) > Date.parse(observation.updated_at) ||
      now - Date.parse(p.observed_at) > 5000 || now < Date.parse(p.observed_at) ||
      !Array.isArray(p.recent) || p.recent.length > 10) return null;
  if (p.recent.some(row => !row || typeof row.observed_at !== "string" ||
      !Number.isFinite(Date.parse(row.observed_at)) || !row.progress ||
      !trends.includes(row.progress.trend) || typeof row.progress.stalled_seconds !== "number" ||
      !Number.isFinite(row.progress.stalled_seconds) || row.progress.stalled_seconds < 0)) return null;
  return p as unknown as EvaluatedProgress;
}
