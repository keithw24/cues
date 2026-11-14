import type { SupabaseClient } from "@supabase/supabase-js";

export class StationSignInRequired extends Error {
  constructor() { super("Sign in to connect a station."); }
}
async function currentUser(client: SupabaseClient) {
  try {
    const { data, error } = await client.auth.getUser();
    if (error || !data.user) throw new StationSignInRequired();
    return data.user;
  } catch (error) {
    if (error instanceof StationSignInRequired) throw error;
    throw new Error("Could not verify your sign-in. Check your connection and try again.");
  }
}
function stations(data: unknown): string[] {
  if (!Array.isArray(data) || data.some(row => !row ||
      typeof row.station_id !== "string" || !row.station_id.trim()))
    throw new Error("Invalid station response");
  return [...new Set(data.map(row => row.station_id as string))].sort();
}
export async function readStationMemberships(client: SupabaseClient): Promise<string[]> {
  const user = await currentUser(client);
  try {
    const { data, error } = await client.from("station_teachers").select("station_id")
      .eq("teacher_id", user.id).abortSignal(AbortSignal.timeout(12000));
    if (error) throw error;
    return stations(data);
  } catch {
    throw new Error("Station access could not be loaded. Try again.");
  }
}
export async function redeemStationCode(client: SupabaseClient, code: string): Promise<string> {
  if (!code.trim()) throw new Error("Enter a pairing code.");
  await currentUser(client);
  try {
    const { data, error } = await client.rpc("redeem_station_pairing_code", { code: code.trim() })
      .abortSignal(AbortSignal.timeout(12000));
    if (error?.code === "42501") throw new StationSignInRequired();
    if (error?.code === "22023")
      throw new Error("That pairing code is invalid or no longer available.");
    if (error) throw error;
    const rows = stations(data);
    if (!Array.isArray(data) || data.length !== 1 || rows.length !== 1) throw new Error();
    return rows[0];
  } catch (error) {
    if (error instanceof StationSignInRequired) throw error;
    if (error instanceof Error && error.message === "That pairing code is invalid or no longer available.") throw error;
    throw new Error("Could not connect the station. Check your connection and try again.");
  }
}
