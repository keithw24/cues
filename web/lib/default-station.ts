import type { SupabaseClient } from "@supabase/supabase-js";
import { StationSignInRequired } from "./station-pairing.ts";

export type DefaultStation = { id: string; name: string | null; created: boolean };

/** Station ids look like S1, S2, ... but any short URL-safe id is accepted. */
const STATION_ID = /^[A-Za-z0-9_-]{1,64}$/;

export function parseDefaultStation(data: unknown): DefaultStation {
  const row = data as { station_id?: unknown; name?: unknown; created?: unknown } | null;
  if (
    !row ||
    typeof row !== "object" ||
    typeof row.station_id !== "string" ||
    !STATION_ID.test(row.station_id) ||
    (row.name != null && typeof row.name !== "string") ||
    typeof row.created !== "boolean"
  )
    throw new Error("Unexpected response from your classroom camera");
  return { id: row.station_id, name: (row.name as string | null) ?? null, created: row.created };
}

/**
 * The signed-in teacher's one persistent default station, created on first use.
 * The database derives the teacher from the sign-in (auth.uid()): nothing here
 * sends a teacher or station owner, so a browser cannot ask for someone else's.
 */
export async function resolveDefaultStation(client: SupabaseClient): Promise<DefaultStation> {
  let response;
  try {
    response = await client
      .rpc("get_or_create_my_default_station")
      .abortSignal(AbortSignal.timeout(12000));
  } catch {
    throw new Error("Your classroom camera could not be loaded. Check your connection and try again.");
  }
  if (response.error?.code === "42501") throw new StationSignInRequired();
  if (response.error)
    throw new Error("Your classroom camera could not be loaded. Check your connection and try again.");
  try {
    return parseDefaultStation(response.data);
  } catch {
    throw new Error("Your classroom camera could not be loaded. Check your connection and try again.");
  }
}
