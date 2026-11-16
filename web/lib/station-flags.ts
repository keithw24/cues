import type { SupabaseClient } from "@supabase/supabase-js";
import { SEAT_ID, STATION_ID } from "./ids.ts";

/**
 * The "Last hour" timeline: when children were flagged.
 *
 * One read of the signed-in teacher's own sessions at their station: reviews requested
 * (any status, so closed ones still show) and vision's own flags. Only the seat, the kind
 * and the time come back; scores, expression data and event details never do.
 */
export type FlagKind = "review" | "review_needed" | "no_progress";
export type StationFlag = { id: string; seat_id: string; kind: FlagKind; at: string };

const KINDS: readonly string[] = ["review", "review_needed", "no_progress"];

export function parseStationFlags(data: unknown): StationFlag[] {
  if (!Array.isArray(data)) throw new Error("Invalid flags response");
  return data.map((row, index) => {
    const r = row as { seat_id?: unknown; kind?: unknown; at?: unknown } | null;
    if (
      !r ||
      typeof r.seat_id !== "string" ||
      !SEAT_ID.test(r.seat_id) ||
      typeof r.kind !== "string" ||
      !KINDS.includes(r.kind) ||
      typeof r.at !== "string" ||
      !Number.isFinite(Date.parse(r.at))
    )
      throw new Error("Invalid flags response");
    return {
      // Stable across refreshes: the same moment keeps the same mark.
      id: `${r.kind}:${r.seat_id}:${r.at}:${index}`,
      seat_id: r.seat_id,
      kind: r.kind as FlagKind,
      at: r.at,
    };
  });
}

/** Plain words for a teacher: a flag is a moment someone was flagged, not a judgement. */
export function flagLabel(kind: FlagKind, name: string): string {
  if (kind === "review") return `${name} flagged for review`;
  if (kind === "review_needed") return `${name} flagged: needs review`;
  return `${name} flagged: no progress`;
}

export async function readStationFlags(
  client: SupabaseClient,
  station: string,
  sinceMs: number,
): Promise<StationFlag[]> {
  if (!STATION_ID.test(station)) throw new Error("Invalid station");
  try {
    const { data, error } = await client
      .rpc("read_station_flags", {
        p_station_id: station,
        p_since: new Date(sinceMs).toISOString(),
      })
      .abortSignal(AbortSignal.timeout(12000));
    if (error) throw error;
    return parseStationFlags(data);
  } catch {
    throw new Error("The timeline could not be loaded.");
  }
}
