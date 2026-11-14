"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { seatViews, statuses, type SeatView } from "@/lib/dashboard";
import { watchDashboard, type FeedState } from "@/lib/dashboard-feed";
import { createDashboardClient } from "@/lib/supabase";

const INITIAL: FeedState = {
  snapshot: null,
  connection: "connecting",
  loading: true,
  error: null,
};

function SeatCard({ seat }: { seat: SeatView }) {
  const status = seat.state ? statuses[seat.state.status] : null;
  return (
    <article
      className={`seat-card tone-${status?.tone ?? "neutral"}`}
      aria-labelledby={`seat-${seat.id}`}
    >
      <div className="seat-heading">
        <h3 id={`seat-${seat.id}`}>{seat.display_name}</h3>
        {seat.is_simulated ? (
          <span className="sim-badge">
            SIM<span className="sr-only"> · Simulated seat</span>
          </span>
        ) : null}
      </div>
      <p className="seat-status">
        <span className="status-mark" aria-hidden="true" />
        {status?.label ?? "Awaiting observation"}
      </p>
      <p className="status-detail">
        {status?.detail ?? "No state has been received for this seat yet."}
      </p>
      <dl className="seat-facts">
        <div>
          <dt>Current activity</dt>
          <dd>{seat.activity}</dd>
        </div>
        <div>
          <dt>Match score</dt>
          <dd>
            {seat.state?.task_score != null &&
            seat.state.status !== "tracking_lost"
              ? seat.state.task_score.toFixed(2)
              : "—"}
          </dd>
        </div>
      </dl>
      <div className="seat-footer">
        <span>{seat.id}</span>
        <span>
          {seat.state ? (
            <>
              Updated{" "}
              <time dateTime={seat.state.updated_at}>
                {new Intl.DateTimeFormat(undefined, {
                  hour: "numeric",
                  minute: "2-digit",
                  second: "2-digit",
                }).format(new Date(seat.state.updated_at))}
              </time>
            </>
          ) : (
            "No observation yet"
          )}
        </span>
      </div>
    </article>
  );
}

export default function Dashboard() {
  const [feed, setFeed] = useState<FeedState>(INITIAL);
  const [attempt, setAttempt] = useState(0);
  const [client] = useState(() => {
    try {
      return createDashboardClient();
    } catch {
      return null;
    }
  });
  const configurationError = client === null;

  useEffect(() => {
    if (!client) return;
    const subscription = watchDashboard(client, setFeed);
    const offline = () => subscription.disconnect();
    // Recreate even after a brief interruption: the old socket might never emit
    // another SUBSCRIBED event, leaving a synthetic offline state stuck on screen.
    const online = () => setAttempt((n) => n + 1);
    window.addEventListener("offline", offline);
    window.addEventListener("online", online);
    return () => {
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", online);
      subscription.dispose();
    };
  }, [attempt, client]);

  const seats = feed.snapshot ? seatViews(feed.snapshot) : [];
  const live =
    !configurationError &&
    feed.connection === "connected" &&
    !feed.error;
  const connectionLabel = configurationError
    ? "Connection not configured"
    : feed.error
      ? "Data unavailable"
      : live
        ? "Live updates connected"
        : feed.connection === "disconnected"
          ? "Updates disconnected"
          : "Connecting to live updates";
  const stationIds = [...new Set(seats.map((s) => s.station_id))];

  return (
    <div className="dashboard-shell">
      <header className="app-header">
        <Link className="wordmark" href="/" aria-label="Cues home">
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          Cues<span className="wordmark-period">.</span>
        </Link>
        <span className="header-description">
          A little clarity. A little support.
        </span>
        <span className="teacher-label">Teacher dashboard</span>
      </header>
      <main id="main-content" className="dashboard-main">
        <div className="page-heading">
          <div>
            <h1>A view of your classroom.</h1>
            <p>Follow each seat’s activity, one observation at a time.</p>
          </div>
          <div
            className={`connection-state ${live ? "is-live" : ""}`}
            role="status"
          >
            <span aria-hidden="true" />
            {connectionLabel}
          </div>
        </div>
        {configurationError ? (
          <section className="notice" role="alert">
            <h2>The dashboard isn’t connected yet.</h2>
            <p>
              Add the project URL and publishable key to{" "}
              <code>web/.env.local</code>, then restart the web server.
            </p>
          </section>
        ) : null}
        {!configurationError &&
        (feed.error || feed.connection === "disconnected") ? (
          <div className="notice" role="alert">
            <div>
              <h2>
                {feed.error
                  ? "We couldn’t refresh the seats."
                  : "Live updates are paused."}
              </h2>
              <p>
                {feed.snapshot
                  ? "Showing the last loaded state. Recent changes may be missing."
                  : "Check your connection, then try again."}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setAttempt((n) => n + 1)}
              disabled={feed.loading}
            >
              Reconnect
            </button>
          </div>
        ) : null}
        {!configurationError &&
        !feed.snapshot &&
        feed.loading &&
        !feed.error ? (
          <section className="loading-state" role="status">
            <span className="loading-line" aria-hidden="true" />
            <h2>Getting your seats ready…</h2>
            <p>Loading the latest activity and status.</p>
          </section>
        ) : null}
        {feed.snapshot ? (
          <>
            <div className="overview-line">
              <h2>
                Seat overview <span>{seats.length}</span>
              </h2>
              <p>
                {seats.every((seat) => seat.is_simulated) && seats.length > 0
                  ? "Simulated seats · Demo data only"
                  : "Current seat observations"}
              </p>
            </div>
            {seats.length === 0 ? (
              <section className="empty-state">
                <h3>No seats to show yet.</h3>
                <p>
                  Once simulated seats are available, their activity and status
                  will appear here.
                </p>
                <button
                  type="button"
                  onClick={() => setAttempt((n) => n + 1)}
                  disabled={feed.loading}
                >
                  Check again
                </button>
              </section>
            ) : (
              stationIds.map((stationId) => (
                <section
                  className="station-section"
                  key={stationId}
                  aria-labelledby={`station-${stationId}`}
                  aria-busy={feed.loading}
                >
                  <div className="station-heading">
                    <h3 id={`station-${stationId}`}>
                      {feed.snapshot?.stations.find((s) => s.id === stationId)
                        ?.name ?? stationId}
                    </h3>
                    <span>{stationId}</span>
                  </div>
                  <div className="seat-grid">
                    {seats
                      .filter((seat) => seat.station_id === stationId)
                      .map((seat) => (
                        <SeatCard key={seat.id} seat={seat} />
                      ))}
                  </div>
                </section>
              ))
            )}
            <p className="observation-note">
              A match score describes a gesture match, not a probability.
              Tracking pauses are never failed attempts.
            </p>
          </>
        ) : null}
      </main>
      <footer className="app-footer">
        <span>Built around the teacher.</span>
        <span>Student camera images and video stay local.</span>
      </footer>
    </div>
  );
}
