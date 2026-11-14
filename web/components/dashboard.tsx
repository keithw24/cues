"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  attentionKey,
  needsReview,
  seatViews,
  statuses,
  type SeatView,
} from "@/lib/dashboard";
import { watchDashboard, type FeedState } from "@/lib/dashboard-feed";
import { createDashboardClient } from "@/lib/supabase";
import { Card } from "@/components/ui/card";
import LocalClassroomFeed from "@/components/local-classroom-feed";

const INITIAL: FeedState = {
  snapshot: null,
  connection: "connecting",
  loading: true,
  error: null,
};
const observationTime = (value: string) =>
  new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));

function SeatDetails({
  seat,
  close,
  headingRef,
}: {
  seat: SeatView;
  close: () => void;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
}) {
  const status = seat.state ? statuses[seat.state.status] : null;
  const score =
    seat.state?.status === "tracking_lost" ? null : seat.state?.task_score;
  return (
    <section
      className="seat-details"
      aria-labelledby="detail-heading"
      onKeyDown={(event) => {
        if (event.key === "Escape") close();
      }}
    >
      <header className="panel-heading">
        <h2 id="detail-heading" ref={headingRef} tabIndex={-1}>
          {seat.display_name}
        </h2>
        <button className="text-button" onClick={close} type="button">
          Close details
        </button>
      </header>
      <div className="detail-body">
        <p
          className={`detail-status ${needsReview(seat) ? "needs-review" : ""}`}
        >
          {status?.label ?? "Awaiting observation"}
        </p>
        <p className="detail-description">
          {status?.detail ?? "No observation has been received for this seat."}
        </p>
        <dl className="detail-facts">
          <div>
            <dt>Current activity</dt>
            <dd>{seat.activity}</dd>
          </div>
          <div>
            <dt>Match score</dt>
            <dd>{score == null ? "Unavailable" : score.toFixed(2)}</dd>
          </div>
          <div>
            <dt>Last observation</dt>
            <dd>
              {seat.state ? (
                <time dateTime={seat.state.updated_at}>
                  {observationTime(seat.state.updated_at)}
                </time>
              ) : (
                "No observation yet"
              )}
            </dd>
          </div>
        </dl>
        {seat.is_simulated ? (
          <p className="detail-simulation">Simulated seat · {seat.id}</p>
        ) : null}
        <section className="detail-section">
          <h3>Recent progress</h3>
          <p>Progress history is not available yet.</p>
        </section>
        <section className="detail-section">
          <h3>Agent assessment</h3>
          <p>No assessment has been received.</p>
        </section>
        <p className="detail-footnote">
          Match scores describe gesture similarity, not probabilities.
        </p>
      </div>
    </section>
  );
}

export default function Dashboard() {
  const [feed, setFeed] = useState<FeedState>(INITIAL);
  const [attempt, setAttempt] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState<Set<string>>(() => new Set());
  const detailsHeading = useRef<HTMLHeadingElement>(null);
  const attentionHeading = useRef<HTMLHeadingElement>(null);
  const detailOpener = useRef<HTMLButtonElement | null>(null);
  const seatButtons = useRef(new Map<string, HTMLButtonElement>());
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
    const online = () => setAttempt((n) => n + 1);
    window.addEventListener("offline", offline);
    window.addEventListener("online", online);
    return () => {
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", online);
      subscription.dispose();
    };
  }, [attempt, client]);
  useEffect(() => {
    if (selectedId) detailsHeading.current?.focus();
  }, [selectedId]);

  const seats = feed.snapshot ? seatViews(feed.snapshot) : [];
  const selected = seats.find((seat) => seat.id === selectedId);
  const reviewSeats = seats.filter(needsReview);
  const queue = reviewSeats
    .filter((seat) => !dismissed.has(attentionKey(seat)))
    .sort(
      (a, b) =>
        Number(b.state?.status === "needs_help") -
          Number(a.state?.status === "needs_help") || a.id.localeCompare(b.id),
    );
  const activityNames = [
    ...new Set(
      seats
        .filter((seat) => seat.state?.activity_id)
        .map((seat) => seat.activity),
    ),
  ];
  const activity = !feed.snapshot
    ? "Activity unavailable"
    : activityNames.length > 1
      ? "Multiple activities"
      : (activityNames[0] ?? "No activity assigned");
  const live =
    !configurationError && feed.connection === "connected" && !feed.error;
  const connectionLabel = configurationError
    ? "Not configured"
    : feed.error
      ? "Data unavailable"
      : live
        ? "Updates live"
        : feed.connection === "disconnected"
          ? "Updates disconnected"
          : "Connecting to updates";
  const selectSeat = (seat: SeatView, opener: HTMLButtonElement) => {
    detailOpener.current = opener;
    setSelectedId(seat.id);
  };
  const closeDetails = () => {
    setSelectedId(null);
    const opener = detailOpener.current;
    if (opener?.isConnected) opener.focus();
    else if (selectedId) seatButtons.current.get(selectedId)?.focus();
  };
  const dismiss = (seat: SeatView) => {
    setDismissed((current) => new Set([...current, attentionKey(seat)]));
    attentionHeading.current?.focus();
  };

  return (
    <div className="dashboard-shell">
      <header className="app-header">
        <Link className="wordmark" href="/" aria-label="Cues home">
          Cues
        </Link>
        <span className="header-divider" aria-hidden="true" />
        <span className="header-activity">{activity}</span>
        <div
          className={`connection-state ${live ? "is-live" : ""}`}
          role="status"
        >
          {connectionLabel}
        </div>
        <button
          className="end-session"
          type="button"
          disabled
          aria-describedby="session-unavailable"
        >
          End session
        </button>
        <span id="session-unavailable" className="sr-only">
          Session controls are not connected in this dashboard.
        </span>
      </header>
      <main id="main-content" className="dashboard-main">
        <h1 className="sr-only">Classroom monitoring</h1>
        <div className="workspace-toolbar">
          <span>
            Classroom
            {seats.length
              ? ` · ${seats.length} ${seats.length === 1 ? "seat" : "seats"}`
              : ""}
          </span>
          <div className="workspace-tools">
            <span className="simulated-label">
              {seats.length > 0 && seats.every((seat) => seat.is_simulated)
                ? "Simulated classroom"
                : "Seat observations"}
            </span>
            <button
              type="button"
              className="refresh-button"
              onClick={() => setAttempt((n) => n + 1)}
              disabled={!client || feed.loading}
              aria-label="Refresh seats"
            >
              {feed.loading ? "Refreshing…" : "Refresh seats"}
            </button>
          </div>
        </div>
        {configurationError ||
        feed.error ||
        feed.connection === "disconnected" ? (
          <section className="notice" role="alert">
            <div>
              <h2>
                {configurationError
                  ? "Seat updates are not configured"
                  : feed.error
                    ? "Seat data could not be refreshed"
                    : "Seat updates are disconnected"}
              </h2>
              <p>
                {configurationError
                  ? "Connect this dashboard to the classroom data source."
                  : feed.snapshot
                    ? "Showing the last loaded observations. Recent changes may be missing."
                    : "Check your connection and try again."}
              </p>
            </div>
            {!configurationError ? (
              <button
                type="button"
                disabled={feed.loading}
                onClick={() => setAttempt((n) => n + 1)}
              >
                Reconnect updates
              </button>
            ) : null}
          </section>
        ) : null}
        <div className="monitor-workspace">
          <div className="monitor-main">
            <LocalClassroomFeed activity={activity} />
            <section className="seat-strip" aria-labelledby="seats-heading">
              <header className="strip-heading">
                <h2 id="seats-heading">Seats</h2>
                <span>
                  {reviewSeats.length
                    ? `${reviewSeats.length} need review`
                    : "Current observations"}
                </span>
              </header>
              {!feed.snapshot ? (
                <p className="strip-empty" role="status">
                  {feed.loading && !configurationError
                    ? "Loading seat observations…"
                    : "Seat observations unavailable"}
                </p>
              ) : seats.length === 0 ? (
                <p className="strip-empty">No seats to show yet.</p>
              ) : (
                <div className="seat-items">
                  {seats.map((seat) => (
                    <button
                      className={`seat-item ${needsReview(seat) ? "needs-review" : ""} ${selected?.id === seat.id ? "is-selected" : ""}`}
                      key={seat.id}
                      ref={(node) => {
                        if (node) seatButtons.current.set(seat.id, node);
                        else seatButtons.current.delete(seat.id);
                      }}
                      type="button"
                      aria-pressed={selected?.id === seat.id}
                      onClick={(event) => selectSeat(seat, event.currentTarget)}
                    >
                      <span className="seat-item-name">
                        {seat.display_name}
                      </span>
                      <span className="seat-item-status">
                        {seat.state
                          ? statuses[seat.state.status].label
                          : "Awaiting observation"}
                      </span>
                      {seat.is_simulated ? (
                        <span className="sim-badge">SIM</span>
                      ) : null}
                    </button>
                  ))}
                </div>
              )}
            </section>
          </div>
          <Card
            role="complementary"
            className="attention-panel"
            aria-label={selected ? "Seat details" : "Attention queue"}
          >
            {selected ? (
              <SeatDetails
                seat={selected}
                close={closeDetails}
                headingRef={detailsHeading}
              />
            ) : (
              <section aria-labelledby="attention-heading">
                <header className="panel-heading">
                  <h2
                    id="attention-heading"
                    ref={attentionHeading}
                    tabIndex={-1}
                  >
                    Attention
                  </h2>
                  <span
                    className={
                      queue.length
                        ? "attention-count has-items"
                        : "attention-count"
                    }
                  >
                    {feed.snapshot ? queue.length : "—"}
                  </span>
                </header>
                {queue.length ? (
                  <ul className="attention-list">
                    {queue.map((seat) => (
                      <li key={attentionKey(seat)}>
                        <div className="attention-item-heading">
                          <h3>{seat.display_name}</h3>
                          <span className="review-label">Needs Review</span>
                        </div>
                        <p>
                          {seat.state
                            ? statuses[seat.state.status].detail
                            : "Review this seat’s observation."}
                        </p>
                        <div className="attention-actions">
                          <button
                            type="button"
                            onClick={(event) =>
                              selectSeat(seat, event.currentTarget)
                            }
                          >
                            View details
                          </button>
                          <button
                            className="text-button"
                            type="button"
                            onClick={() => dismiss(seat)}
                          >
                            Dismiss
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="queue-empty">
                    <p>
                      {!feed.snapshot
                        ? "Waiting for observations"
                        : reviewSeats.length
                          ? "Review items dismissed"
                          : "No seats need review"}
                    </p>
                    <span>
                      {!feed.snapshot
                        ? "Attention items will appear when seat data is available."
                        : reviewSeats.length
                          ? "Seat statuses remain visible below the classroom feed."
                          : "Seats marked for review or support will appear here."}
                    </span>
                  </div>
                )}
                {dismissed.size > 0 ? (
                  <div className="dismiss-note">
                    <p>
                      Dismiss hides an observation for this visit. New
                      observations can appear again.
                    </p>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => {
                        setDismissed(new Set());
                        attentionHeading.current?.focus();
                      }}
                    >
                      Restore dismissed items
                    </button>
                  </div>
                ) : null}
              </section>
            )}
          </Card>
        </div>
        <footer className="workspace-footer">
          <span>
            Student camera images and video stay on the station laptop.
          </span>
          <span>Session controls are not connected.</span>
        </footer>
      </main>
    </div>
  );
}
