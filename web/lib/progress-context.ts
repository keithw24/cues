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


/** Evaluations are hidden once the agent has not read its station for this long. */
export const AGENT_SILENT_MS = 20_000;

/** Whether the agent's station heartbeat (`station_runtime.agent_seen_at`) is recent. */
export function agentIsAlive(agentSeenAt: string | null, now: number | null): boolean {
  if (agentSeenAt === null || now === null) return false;
  const seen = Date.parse(agentSeenAt);
  return Number.isFinite(seen) && now - seen <= AGENT_SILENT_MS;
}

export type EvaluatedProgress = {
  trend: "improving" | "stalled" | "completed" | "unknown";
  stalled_seconds: number;
  /** When the current stall began (backend time); null unless the trend is stalled. */
  stalled_since: string | null;
  observed_at: string;
  recent: {observed_at: string; progress: {trend: string; stalled_seconds: number}}[];
};
/** Only backend output for this task revision, while the agent is alive, is displayable.
 * Progress is published only when it changes, so its age says nothing; the agent heartbeat does. */
export function evaluatedProgress(observation: SeatState | null | undefined,
  now: number = Date.now(), agentAlive = false): EvaluatedProgress | null {
  if (!agentAlive || !observation || observation.tracking_valid !== true || observation.status === "tracking_lost") return null;
  const raw = observation.evaluated_progress;
  if (!raw || typeof raw !== "object") return null;
  const p = raw as Record<string, unknown>;
  const trends = ["improving", "stalled", "completed", "unknown"];
  if (p.session_id !== observation.session_id || p.activity_id !== observation.activity_id ||
      p.session_revision !== observation.session_revision || !trends.includes(String(p.trend)) ||
      typeof p.stalled_seconds !== "number" || !Number.isFinite(p.stalled_seconds) || p.stalled_seconds < 0 ||
      typeof p.observed_at !== "string" || !Number.isFinite(Date.parse(p.observed_at)) ||
      Date.parse(p.observed_at) > Date.parse(observation.updated_at) ||
      now + 2000 < Date.parse(p.observed_at) ||
      (p.stalled_since != null && (typeof p.stalled_since !== "string" || !Number.isFinite(Date.parse(p.stalled_since)))) ||
      !Array.isArray(p.recent) || p.recent.length > 10) return null;
  if (p.recent.some(row => !row || typeof row.observed_at !== "string" ||
      !Number.isFinite(Date.parse(row.observed_at)) || !row.progress ||
      !trends.includes(row.progress.trend) || typeof row.progress.stalled_seconds !== "number" ||
      !Number.isFinite(row.progress.stalled_seconds) || row.progress.stalled_seconds < 0)) return null;
  return p as unknown as EvaluatedProgress;
}
