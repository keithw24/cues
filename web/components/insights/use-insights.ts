import { useEffect, useState } from "react";
import type { SupabaseClient } from "@supabase/supabase-js";
import { createDashboardClient } from "@/lib/supabase";
import { fetchInsights, type Insights } from "@/lib/insights";

export type InsightsAuth = "checking" | "signed-out" | "signed-in";
type Done = { key: string; data?: Insights; error?: string };
export type ActivityOption = { id: string; name: string };

/** The signed-in teacher's insights for a number of days and an optional activity: one request
 * on load and one each time the choice changes. No polling and no realtime. */
export function useInsights(days: number, activity: string | null) {
  const [client] = useState<SupabaseClient | null>(() => {
    try {
      return createDashboardClient(true);
    } catch {
      return null;
    }
  });
  const [auth, setAuth] = useState<InsightsAuth>("checking");
  const [done, setDone] = useState<Done | null>(null);
  const [activities, setActivities] = useState<ActivityOption[]>([]);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!client) return;
    const { data } = client.auth.onAuthStateChange((_event, session) => {
      setAuth(session?.user ? "signed-in" : "signed-out");
    });
    return () => data.subscription.unsubscribe();
  }, [client]);

  // The activity choices come from the activities table, once, so they do not shrink when a
  // filter is on.
  useEffect(() => {
    if (!client || auth !== "signed-in") return;
    let stale = false;
    void client
      .from("activities")
      .select("id,name")
      .order("name")
      .then(({ data }) => {
        if (!stale && data) setActivities(data as ActivityOption[]);
      });
    return () => {
      stale = true;
    };
  }, [client, auth]);

  const key = `${days}|${activity ?? ""}|${reload}`;
  useEffect(() => {
    if (!client || auth !== "signed-in") return;
    let stale = false;
    const to = new Date();
    const from = new Date(to.getTime() - days * 86_400_000);
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    fetchInsights(client, { from, to }, activity, tz).then(
      (data) => {
        if (!stale) setDone({ key, data });
      },
      (cause: unknown) => {
        if (!stale)
          setDone({
            key,
            error: cause instanceof Error ? cause.message : "Could not load your insights.",
          });
      },
    );
    return () => {
      stale = true;
    };
  }, [client, auth, days, activity, key]);

  const current = done && done.key === key ? done : null;
  return {
    configured: client !== null,
    auth,
    activities,
    loading: auth === "signed-in" && current === null,
    // While a new choice loads, keep showing the last answer (dimmed by the page).
    data: current?.data ?? done?.data ?? null,
    error: current?.error ?? null,
    retry: () => setReload((n) => n + 1),
  };
}
