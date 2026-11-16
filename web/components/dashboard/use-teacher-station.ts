import { useEffect, useState } from "react";
import {
  resolveDefaultStation,
  StationSignInRequired,
} from "@/lib/default-station";
import { createDashboardClient } from "@/lib/supabase";
import { startLocalVisionSync } from "@/lib/local-vision";

/** Who the dashboard is for: unknown until the sign-in check returns. */
export type Account =
  | { state: "checking" }
  | { state: "signed-out" }
  | { state: "finding" }
  | { state: "ready"; station: string }
  | { state: "error"; message: string };

type Options = {
  stationId: string;
  sessionControlsEnabled: boolean;
  teacherLoginEnabled: boolean;
  reviewActionsEnabled: boolean;
  visionStationConfigEnabled: boolean;
};

/** The Supabase client and the station this dashboard is about: the override, else the
 * signed-in teacher's own default station. Also keeps this laptop's vision on that station. */
export function useTeacherStation({
  stationId,
  sessionControlsEnabled,
  teacherLoginEnabled,
  reviewActionsEnabled,
  visionStationConfigEnabled,
}: Options) {
  const [client] = useState(() => {
    try {
      return createDashboardClient(
        sessionControlsEnabled || teacherLoginEnabled || reviewActionsEnabled,
      );
    } catch {
      return null;
    }
  });
  const configurationError = client === null;
  // The station this dashboard is about: the override, else the signed-in teacher's own
  // default station (created on first sign-in). Empty while signed out or still loading.
  const stationOverride = stationId.trim();
  const resolvesStation =
    !stationOverride && (sessionControlsEnabled || teacherLoginEnabled);
  const [account, setAccount] = useState<Account>({ state: "checking" });
  const station =
    stationOverride || (account.state === "ready" ? account.station : "");
  // Tell this laptop's vision service the signed-in teacher's resolved station.
  // The result isn't shown as a caption: the camera card itself says when the
  // camera can't be reached.
  useEffect(() => {
    if (!visionStationConfigEnabled || !client || !station) return;
    return startLocalVisionSync(client, station);
  }, [client, station, visionStationConfigEnabled]);
  useEffect(() => {
    if (!client || !resolvesStation) return;
    let disposed = false;
    let latest = 0;
    const resolve = async (signedIn: boolean) => {
      const mine = ++latest;
      if (!signedIn) {
        setAccount({ state: "signed-out" });
        return;
      }
      setAccount({ state: "finding" });
      try {
        const found = await resolveDefaultStation(client);
        if (!disposed && mine === latest)
          setAccount({ state: "ready", station: found.id });
      } catch (cause) {
        if (disposed || mine !== latest) return;
        setAccount(
          cause instanceof StationSignInRequired
            ? { state: "signed-out" }
            : {
                state: "error",
                message:
                  cause instanceof Error
                    ? cause.message
                    : "Your classroom camera could not be loaded.",
              },
        );
      }
    };
    const initial = latest;
    // undefined until the first read: tab focus fires SIGNED_IN again for the
    // same teacher, which must not reset the classroom.
    let userId: string | null | undefined;
    void client.auth.getSession().then(({ data }) => {
      if (disposed || latest !== initial) return;
      userId = data.session?.user.id ?? null;
      void resolve(Boolean(data.session));
    });
    const { data } = client.auth.onAuthStateChange((event, session) => {
      if (event === "INITIAL_SESSION" || event === "TOKEN_REFRESHED") return;
      const next = session?.user.id ?? null;
      if (userId !== undefined && next === userId) return;
      userId = next;
      ++latest; // Immediately invalidate in-flight work for the previous identity.
      // A different account: never keep the previous teacher's station on screen.
      setAccount(session ? { state: "finding" } : { state: "signed-out" });
      // Defer: Supabase calls inside this callback can deadlock the auth lock.
      setTimeout(() => {
        if (!disposed) void resolve(Boolean(session));
      }, 0);
    });
    return () => {
      disposed = true;
      data.subscription.unsubscribe();
    };
  }, [client, resolvesStation]);
  return { client, configurationError, resolvesStation, account, station };
}
