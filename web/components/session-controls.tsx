"use client";
import Link from "next/link";
import { WorkspaceIcon } from "@/components/workspace-icon";
import { useEffect, useRef, useState } from "react";
import type { SupabaseClient } from "@supabase/supabase-js";
import {
  changeSession,
  readSession,
  sessionOwnership,
  sessionActions,
  sessionControlState,
  stationSyncLabel,
  type SessionSnapshot,
} from "@/lib/session-controls";

export function SessionControls({
  client,
  station,
  stationMessage,
  onActivity,
  teacherLoginEnabled = false,
}: {
  client: SupabaseClient;
  station: string;
  /** Shown while the signed-in teacher's station is being found (or cannot be). */
  stationMessage?: string;
  onActivity: (label: string) => void;
  teacherLoginEnabled?: boolean;
}) {
  const [user, setUser] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<SessionSnapshot | null>(null);
  const [selection, setSelection] = useState("");
  const [busy, setBusy] = useState(false);
  const [pendingAction, setPendingAction] = useState<
    "start" | "change" | "end" | null
  >(null);
  const [error, setError] = useState<string | null>(null);
  // Why the session never loaded (e.g. the camera is not linked to you),
  // kept apart from later action, sign-out or live-update errors.
  const [loadError, setLoadError] = useState<string | null>(null);
  const selectRef = useRef<HTMLSelectElement>(null);
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
      setLoadError(null);
      onActivity(user ? "Loading activity…" : "Sign in to manage activities");
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
        setLoadError(null);
        setRefreshRequired(false);
        onActivity(
          next.session
            ? (next.activities.find(
                (a) => a.id === next.session?.current_activity_id,
              )?.name ?? "Activity unavailable")
            : "No activity running",
        );
      } catch (cause) {
        if (
          !disposed &&
          epoch === generation.current &&
          id === request.current
        ) {
          const message =
            cause instanceof Error
              ? cause.message
              : "Session could not be refreshed. Check your camera link and retry.";
          if (!loaded) {
            onActivity("Activity unavailable");
            setLoadError(message);
          }
          setError(message);
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
          // A disconnected live channel does not invalidate a successful RPC
          // snapshot. Revision checks still protect actions; polling can recover.
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
    setPendingAction(
      activityId === null ? "end" : snapshot.session ? "change" : "start",
    );
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
      // A successful change removes the Change button; keep focus nearby.
      if (activityId !== null && snapshot.session)
        requestAnimationFrame(() => selectRef.current?.focus());
      onActivity(
        result.ended_at
          ? "No activity running"
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
        setPendingAction(null);
        refreshAfterAction.current?.();
      }
    }
  }
  if (!station)
    return (
      <p className="session-line" role="status">
        {stationMessage || "No classroom camera is set up yet."}
      </p>
    );
  if (!user && teacherLoginEnabled)
    return (
      <Link className="ws-pill is-dark" href="/login">
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
  const controlState = sessionControlState(snapshot, refreshRequired);
  const session = snapshot?.session ?? null;
  const actions = sessionActions(snapshot, selection);
  // One short line under the controls. Only sessions that need the teacher's
  // attention say who owns them; ids stay out of the interface.
  const ownership = !snapshot
    ? null
    : !session
      ? "Pick an activity to start."
      : sessionOwnership(session, user) === "unowned"
        ? "An earlier session is still open. End it, then start yours."
        : sessionOwnership(session, user) === "other"
          ? "Another teacher started this session."
          : null;
  const sync = snapshot ? stationSyncLabel(snapshot, now) : null;
  // Join what needs the teacher: a session that isn't theirs, and a camera
  // that isn't in step (with or without a session). Calm states stay hidden.
  const attention =
    [
      session && ownership !== "Pick an activity to start." ? ownership : null,
      sync && sync !== "Activity synced" && sync !== "Camera idle" ? sync : null,
    ]
      .filter(Boolean)
      .join(" · ") || null;
  const refreshButton = (
    <button
      type="button"
      className="ws-icon-button"
      aria-label="Refresh activity"
      title="Refresh activity"
      disabled={busy}
      onClick={() => setRefreshKey((n) => n + 1)}
    >
      <WorkspaceIcon name="refresh" />
    </button>
  );
  // The session could not load: say so plainly instead of showing controls
  // that can't act, with a way to retry.
  if (!snapshot && loadError && controlState === "refresh")
    return (
      <div className="session-controls is-blocked" aria-busy={busy}>
        <p className="session-line" role="alert">
          {loadError}
        </p>
        <div className="session-row">{refreshButton}</div>
      </div>
    );
  return (
    <div className="session-controls" aria-busy={busy}>
      <div className="session-row">
        <label className="sr-only" htmlFor="session-activity">
          Activity
        </label>
        <select
          id="session-activity"
          ref={selectRef}
          value={selection}
          onChange={(e) => setSelection(e.target.value)}
          disabled={
            busy || controlState === "loading" || controlState === "refresh"
          }
        >
          <option value="">
            {controlState === "loading"
              ? "Loading activities…"
              : "Pick an activity"}
          </option>
          {snapshot?.activities.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
        {actions.primary ? (
          <button
            type="button"
            className="ws-pill is-dark"
            disabled={
              busy ||
              refreshRequired ||
              (actions.primary === "start" && !selection)
            }
            onClick={() => void act(selection)}
          >
            {actions.primary === "start"
              ? pendingAction === "start"
                ? "Starting…"
                : "Start"
              : pendingAction === "change"
                ? "Changing…"
                : "Change activity"}
          </button>
        ) : null}
        {actions.end ? (
          <button
            type="button"
            className="ws-pill"
            disabled={busy || refreshRequired}
            onClick={() => void act(null)}
          >
            {pendingAction === "end" ? "Ending…" : "End"}
          </button>
        ) : null}
        {refreshButton}
      </div>
      {/* Only what needs the teacher: a loading or setup message, a session
          that isn't theirs, or a camera that isn't in step. "Synced" and
          "Pick an activity" say nothing the controls don't already show. */}
      {stationMessage || attention ? (
        <p className="session-line" role="status">
          {stationMessage || attention}
        </p>
      ) : null}
      {error ? (
        <p className="session-line is-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
