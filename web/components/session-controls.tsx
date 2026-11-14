"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { SupabaseClient } from "@supabase/supabase-js";
import {
  changeSession,
  readSession,
  sessionOwnership,
  stationSyncLabel,
  type SessionSnapshot,
} from "@/lib/session-controls";

export function SessionControls({
  client,
  station,
  onActivity,
  teacherLoginEnabled = false,
}: {
  client: SupabaseClient;
  station: string;
  onActivity: (label: string) => void;
  teacherLoginEnabled?: boolean;
}) {
  const [user, setUser] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<SessionSnapshot | null>(null);
  const [selection, setSelection] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshRequired, setRefreshRequired] = useState(false);
  const [now, setNow] = useState(0);
  const refreshAfterAction = useRef<(() => void) | null>(null);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const needsRefresh = useRef(false);
  const locked = useRef(false);
  const generation = useRef(0);
  const request = useRef(0);
  useEffect(() => {
    const { data } = client.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user.id ?? null);
    });
    return () => data.subscription.unsubscribe();
  }, [client]);
  useEffect(() => {
    const epoch = ++generation.current;
    let disposed = false;
    let loaded = false;
    let refreshing = false;
    let refreshAgain = false;
    needsRefresh.current = false;
    queueMicrotask(() => {
      if (disposed) return;
      setSnapshot(null);
      setSelection("");
      setRefreshRequired(false);
      setError(null);
      onActivity(user ? "Loading session…" : "Sign in to manage activities");
    });
    if (!user || !station) return;
    async function refresh() {
      if (disposed || locked.current || needsRefresh.current) return;
      if (refreshing) {
        refreshAgain = true;
        return;
      }
      refreshing = true;
      const id = ++request.current;
      if (!loaded) setBusy(true);
      try {
        const next = await readSession(client, station);
        if (disposed || epoch !== generation.current || id !== request.current)
          return;
        loaded = true;
        setSnapshot(next);
        setSelection((previous) =>
          previous && next.activities.some((a) => a.id === previous)
            ? previous
            : (next.session?.current_activity_id ?? ""),
        );
        setError(null);
        setRefreshRequired(false);
        onActivity(
          next.session
            ? (next.activities.find(
                (a) => a.id === next.session?.current_activity_id,
              )?.name ?? "Activity unavailable")
            : "No active session",
        );
      } catch {
        if (
          !disposed &&
          epoch === generation.current &&
          id === request.current
        ) {
          if (!loaded) onActivity("Session unavailable");
          setError(
            "Session could not be refreshed. Check your station access and retry.",
          );
          needsRefresh.current = true;
          setRefreshRequired(true);
        }
      } finally {
        refreshing = false;
        if (!disposed && id === request.current) setBusy(false);
        if (refreshAgain && !disposed) {
          refreshAgain = false;
          void refresh();
        }
      }
    }
    refreshAfterAction.current = () => void refresh();
    void refresh();
    const channel = client
      .channel(`session-controls:${station}:${epoch}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "sessions",
          filter: `station_id=eq.${station}`,
        },
        () => void refresh(),
      )
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "station_runtime",
          filter: `station_id=eq.${station}`,
        },
        () => void refresh(),
      )
      .subscribe((status) => {
        if (status === "SUBSCRIBED") void refresh();
        else if (
          ["CHANNEL_ERROR", "TIMED_OUT", "CLOSED"].includes(status) &&
          !disposed
        ) {
          setError(
            "Live session updates are disconnected. Refresh the session before acting.",
          );
          needsRefresh.current = true;
          setRefreshRequired(true);
        }
      });
    const online = () => void refresh();
    window.addEventListener("online", online);
    const timer = setInterval(() => void refresh(), 15000);
    return () => {
      disposed = true;
      refreshAfterAction.current = null;
      generation.current = epoch + 1;
      clearInterval(timer);
      window.removeEventListener("online", online);
      void client.removeChannel(channel);
    };
  }, [client, station, user, refreshKey, onActivity]);
  async function act(activityId: string | null) {
    if (locked.current || !snapshot || refreshRequired) return;
    locked.current = true;
    request.current++;
    const epoch = generation.current;
    setBusy(true);
    setError(null);
    try {
      const result = await changeSession(
        client,
        station,
        snapshot.session,
        activityId,
        user,
      );
      if (epoch !== generation.current) return;
      const next = {
        ...snapshot,
        session: result.ended_at ? null : result,
        latest_session: result,
      };
      setSnapshot(next);
      onActivity(
        result.ended_at
          ? "No active session"
          : (snapshot.activities.find(
              (a) => a.id === result.current_activity_id,
            )?.name ?? "Activity unavailable"),
      );
    } catch {
      if (epoch === generation.current) {
        setError(
          "Action could not be saved. Refresh the session to check its state before retrying.",
        );
        needsRefresh.current = true;
        setRefreshRequired(true);
      }
    } finally {
      locked.current = false;
      if (epoch === generation.current) {
        setBusy(false);
        refreshAfterAction.current?.();
      }
    }
  }
  if (!station)
    return <span role="status">Session station is not configured.</span>;
  if (!user && teacherLoginEnabled)
    return (
      <Link className="primary-button session-login-link" href="/login">
        Teacher sign in
      </Link>
    );
  if (!user)
    return (
      <details className="session-sign-in">
        <summary>Teacher sign in</summary>
        <form
          onSubmit={async (event) => {
            event.preventDefault();
            if (locked.current) return;
            const fields = new FormData(event.currentTarget);
            locked.current = true;
            setBusy(true);
            setError(null);
            let signedIn = false;
            try {
              const { error } = await client.auth.signInWithPassword({
                email: String(fields.get("email")),
                password: String(fields.get("password")),
              });
              if (error)
                setError("Sign-in failed. Check your email and password.");
              else signedIn = true;
            } catch {
              setError("Sign-in could not connect. Try again.");
            } finally {
              locked.current = false;
              setBusy(false);
              if (signedIn) setRefreshKey((n) => n + 1);
            }
          }}
        >
          <label>
            Email
            <input name="email" type="email" autoComplete="username" required />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
            />
          </label>
          <button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
          {error ? <p role="alert">{error}</p> : null}
        </form>
      </details>
    );
  return (
    <div className="session-controls" aria-busy={busy}>
      <label className="sr-only" htmlFor="session-activity">
        Activity
      </label>
      <select
        id="session-activity"
        value={selection}
        onChange={(e) => setSelection(e.target.value)}
        disabled={busy || !snapshot || refreshRequired}
      >
        <option value="">Select activity</option>
        {snapshot?.activities.map((a) => (
          <option key={a.id} value={a.id}>
            {a.name}
          </option>
        ))}
      </select>
      <button
        type="button"
        disabled={
          busy ||
          !snapshot ||
          !selection ||
          refreshRequired ||
          snapshot.session?.current_activity_id === selection
        }
        onClick={() => void act(selection)}
      >
        {busy ? "Updating…" : "Start activity"}
      </button>
      <button
        type="button"
        disabled={busy || !snapshot?.session || refreshRequired}
        onClick={() => void act(null)}
      >
        End session
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => setRefreshKey((n) => n + 1)}
      >
        Refresh session
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() =>
          void client.auth.signOut().then(({ error }) => {
            if (error) setError("Could not sign out. Try again.");
          })
        }
      >
        Sign out
      </button>
      {snapshot ? (
        <span className="session-sync-status" role="status">
          {stationSyncLabel(snapshot, now)}
        </span>
      ) : null}
      {sessionOwnership(snapshot?.session ?? null, user) === "unowned" ? (
        <p className="session-sync-status" role="status">
          This session has no teacher owner, so its reviews stay hidden. End it
          and start an activity to own a new session.
        </p>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
    </div>
  );
}
