import type { SupabaseClient } from "@supabase/supabase-js";
import { STATION_ID } from "./ids.ts";

/**
 * Tell this laptop's vision service which station the signed-in teacher uses.
 *
 * The browser sends only the station the dashboard already resolved for the
 * authenticated teacher, to loopback (never a remote host). No Supabase key
 * or user token is sent. Vision refuses anything that is not from this laptop.
 */
export const LOCAL_VISION_URL = "http://127.0.0.1:8000";
/** Re-send so a restarted vision service picks the station up again. */
export const RESEND_MS = 5000;

export type LocalVisionResult =
  | "configured" // vision switched to this station
  | "unchanged" // vision already had this station
  | "invalid" // not a station id; nothing sent
  | "pinned" // vision is pinned to another station by CUES_STATION_ID
  | "unavailable"; // vision not running or refused

type Fetch = (url: string, init: RequestInit) => Promise<Response>;

export async function configureLocalVision(
  stationId: string | null,
  fetcher: Fetch = fetch,
  base: string = LOCAL_VISION_URL,
): Promise<LocalVisionResult> {
  if (stationId !== null && !STATION_ID.test(stationId)) return "invalid";
  try {
    const response = await fetcher(`${base}/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ station_id: stationId }),
      credentials: "omit",
      signal: AbortSignal.timeout(3000),
    });
    if (response.status === 409) return "pinned";
    if (!response.ok) return "unavailable";
    const body = (await response.json()) as { changed?: unknown };
    return body.changed === true ? "configured" : "unchanged";
  } catch {
    return "unavailable";
  }
}

type Auth = Pick<SupabaseClient, "auth">;

/**
 * While a teacher is signed in, keep the local vision service on `stationId`.
 * Signed out: nothing is sent. Returns a function that stops syncing.
 */
export function startLocalVisionSync(
  client: Auth,
  stationId: string,
  {
    fetcher = fetch,
    base = LOCAL_VISION_URL,
    intervalMs = RESEND_MS,
    onResult,
  }: {
    fetcher?: Fetch;
    base?: string;
    intervalMs?: number;
    onResult?: (result: LocalVisionResult) => void;
  } = {},
): () => void {
  let signedIn = false;
  let stopped = false;
  let sending = false;
  const send = async () => {
    if (stopped || !signedIn || sending) return;
    sending = true;
    try {
      const result = await configureLocalVision(stationId, fetcher, base);
      if (!stopped) onResult?.(result);
    } finally {
      sending = false;
    }
  };
  const { data } = client.auth.onAuthStateChange((_event, session) => {
    signedIn = Boolean(session?.user?.id);
    if (signedIn) void send();
    else void configureLocalVision(null, fetcher, base);
  });
  const timer = setInterval(() => void send(), intervalMs);
  return () => {
    stopped = true;
    clearInterval(timer);
    data.subscription.unsubscribe();
  };
}
