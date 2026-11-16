/** Only a page served from this laptop may read its loopback vision service. */
export function mayConnectLocalFeed(origin: string): boolean {
  try {
    return ["localhost", "127.0.0.1", "[::1]"].includes(new URL(origin).hostname);
  } catch {
    return false;
  }
}
