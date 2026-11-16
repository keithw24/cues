import type { SupabaseClient } from "@supabase/supabase-js";
import { STATION_ID } from "./ids.ts";

/**
 * One camera per station. A second camera working for the same station is refused and
 * paused (the database enforces it). This reads the station's writer row so the dashboard
 * can say so: seeing the warning means a camera is being refused right now.
 */
export type StationWriter = { seen_at: string; contested_at: string | null };

/** The refusal and the holder's last renewal must be this close (both are database times). */
const CONTESTED_WITHIN_MS = 10_000;
/** The holder must have renewed recently by this browser's clock (a generous skew margin). */
const HOLDER_ALIVE_MS = 60_000;

export function parseStationWriter(data: unknown): StationWriter | null {
  if (data == null) return null;
  const row = data as { seen_at?: unknown; contested_at?: unknown };
  if (
    typeof row !== "object" ||
    typeof row.seen_at !== "string" ||
    !Number.isFinite(Date.parse(row.seen_at)) ||
    (row.contested_at != null &&
      (typeof row.contested_at !== "string" ||
        !Number.isFinite(Date.parse(row.contested_at))))
  )
    throw new Error("Invalid response");
  return { seen_at: row.seen_at, contested_at: row.contested_at ?? null };
}

/**
 * True while another camera is being refused: it was refused close to the holder's most
 * recent renewal (it keeps retrying about once a second), and the holder is still running.
 * It clears within seconds once the extra camera stops, and when the holder dies and the
 * other one takes over.
 */
export function cameraConflict(writer: StationWriter | null, now: number): boolean {
  if (!writer?.contested_at) return false;
  const seen = Date.parse(writer.seen_at);
  const contested = Date.parse(writer.contested_at);
  return seen - contested < CONTESTED_WITHIN_MS && now - seen < HOLDER_ALIVE_MS;
}

export const CAMERA_CONFLICT_MESSAGE =
  "Another camera is trying to use this station. Only one camera can use a station " +
  "at a time, so the extra one is paused. Close it, or sign in on that laptop with its own account.";

export async function readStationWriter(
  client: SupabaseClient,
  station: string,
): Promise<StationWriter | null> {
  if (!STATION_ID.test(station)) throw new Error("Invalid station");
  try {
    const { data, error } = await client
      .from("station_writers")
      .select("seen_at,contested_at")
      .eq("station_id", station)
      .abortSignal(AbortSignal.timeout(12000))
      .maybeSingle();
    if (error) throw error;
    return parseStationWriter(data);
  } catch {
    throw new Error("The camera status could not be loaded.");
  }
}
