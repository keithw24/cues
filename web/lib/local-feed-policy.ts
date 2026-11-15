/** Explicit hosted origin only; this does not expose the loopback service publicly. */
export function mayConnectLocalFeed(origin: string, hostedEnabled: boolean,
  hostedOrigin = "https://cues.nyc"): boolean {
  try {
    const url = new URL(origin);
    if (["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) return true;
    return hostedEnabled && url.protocol === "https:" && url.origin === new URL(hostedOrigin).origin;
  } catch { return false; }
}
