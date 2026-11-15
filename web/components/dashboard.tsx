"use client";

import { useEffect, useRef, useState } from "react";
import { seatViews, type SeatView } from "@/lib/dashboard";
import {
  INITIAL_REVIEWS,
  DISABLED_REVIEWS,
  watchTeacherReviews,
  type ReviewFeedState,
} from "@/lib/teacher-review-feed";
import { activityLabel, groupReviewsBySeat } from "@/lib/teacher-reviews";
import { TeacherReviewDetails } from "@/components/teacher-review-details";
import { watchDashboard, type FeedState } from "@/lib/dashboard-feed";
import { resolveDefaultStation } from "@/lib/default-station";
import { StationSignInRequired } from "@/lib/station-pairing";
import { createDashboardClient } from "@/lib/supabase";
import { startLocalVisionSync } from "@/lib/local-vision";
import { Card } from "@/components/ui/card";
import { TeacherReviewActions } from "@/components/teacher-review-actions";
import { SessionControls } from "@/components/session-controls";
import LocalClassroomFeed from "@/components/local-classroom-feed";
import {
  inCameraView,
  isFresh,
  observationPresentation,
  type ObservationOptions,
} from "@/lib/observation-presentation";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { WorkspaceIcon } from "@/components/workspace-icon";
import { ClassroomRoom, type RoomPerson } from "@/components/classroom-room";
import { NextUpCard } from "@/components/next-up";
import { LessonTimeline } from "@/components/lesson-timeline";
import { nextUp } from "@/lib/next-up";
import {
  PersonRowContent,
  ReviewRowContent,
} from "@/components/workspace-rows";

const INITIAL: FeedState = {
  snapshot: null,
  connection: "connecting",
  loading: true,
  error: null,
};
type Presentation = ReturnType<typeof observationPresentation>;
const statusTone = (presentation: Presentation): RoomPerson["tone"] =>
  presentation.needsReview
    ? "review"
    : presentation.currentStatus === "done"
      ? "done"
      : presentation.currentStatus === "in_progress"
        ? "working"
        : "quiet";
const statusIcon = (presentation: Presentation) =>
  presentation.needsReview
    ? "flag"
    : presentation.currentStatus === "done"
      ? "check"
      : presentation.currentStatus === "in_progress"
        ? "working"
        : presentation.currentStatus === "tracking_lost" ||
            presentation.label.startsWith("Tracking")
          ? "hidden"
          : presentation.unavailable
            ? "paused"
            : "time";

function SeatDetails({
  seat,
  close,
  headingRef,
  observationOptions,
}: {
  observationOptions?: ObservationOptions;
  seat: SeatView;
  close: () => void;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
}) {
  // What a teacher needs about one person: their status and task. Scores,
  // ids, tracking and expression internals stay out of the way.
  const presentation = observationPresentation(seat.state, observationOptions);
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
          Back
        </button>
      </header>
      <div className="detail-body">
        <p
          className={`detail-status ${presentation.needsReview ? "needs-review" : ""}`}
        >
          {presentation.label}
        </p>
        <p className="detail-description">{seat.activity}</p>
      </div>
    </section>
  );
}

export default function Dashboard({
  liveProgressEnabled = false,
  personObservationsEnabled = false,
  sessionControlsEnabled = false,
  stationId = "",
  reviewsEnabled = false,
  reviewActionsEnabled = false,
  teacherLoginEnabled = false,
  roomViewEnabled = false,
  themeToggleEnabled = false,
  liveViewEnabled = false,
  visionStationConfigEnabled = false,
}: {
  liveProgressEnabled?: boolean;
  personObservationsEnabled?: boolean;
  sessionControlsEnabled?: boolean;
  /** Explicit dev/test override (CUES_STATION_OVERRIDE). Normally empty: a signed-in
   * teacher's own default station is used. */
  stationId?: string;
  reviewsEnabled?: boolean;
  reviewActionsEnabled?: boolean;
  teacherLoginEnabled?: boolean;
  roomViewEnabled?: boolean;
  themeToggleEnabled?: boolean;
  liveViewEnabled?: boolean;
  visionStationConfigEnabled?: boolean;
}) {
  const [observationNow, setObservationNow] = useState<number | null>(null);
  useEffect(() => {
    if (!personObservationsEnabled) return;
    const tick = () => setObservationNow(Date.now());
    const initial = setTimeout(tick, 0);
    const timer = setInterval(tick, 1000);
    const visible = () => {
      if (!document.hidden) tick();
    };
    document.addEventListener("visibilitychange", visible);
    return () => {
      clearTimeout(initial);
      clearInterval(timer);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [personObservationsEnabled]);
  const [sessionActivity, setSessionActivity] = useState("Session unavailable");
  const [feed, setFeed] = useState<FeedState>(INITIAL);
  const [attempt, setAttempt] = useState(0);
  const [selectedReviewId, setSelectedReviewId] = useState<string | null>(null);
  const attentionHeading = useRef<HTMLHeadingElement>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerToggle = useRef<HTMLButtonElement>(null);
  const drawerClose = useRef<HTMLButtonElement>(null);
  const [reviews, setReviews] = useState<ReviewFeedState>(
    reviewsEnabled ? INITIAL_REVIEWS : DISABLED_REVIEWS,
  );
  const resolvedReviewIds = useRef(new Set<string>());
  const [reviewAttempt, setReviewAttempt] = useState(0);
  const detailsHeading = useRef<HTMLHeadingElement>(null);
  const detailOpener = useRef<HTMLButtonElement | null>(null);
  const seatButtons = useRef(new Map<string, HTMLButtonElement>());
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
  const [defaultStation, setDefaultStation] = useState<{
    id: string | null;
    message: string;
  }>({ id: null, message: "Sign in to manage activities" });
  const station = stationOverride || defaultStation.id || "";
  const [visionMessage, setVisionMessage] = useState("");
  // Tell this laptop's vision service the signed-in teacher's resolved station.
  useEffect(() => {
    if (!visionStationConfigEnabled || !client || !station) return;
    return startLocalVisionSync(client, station, {onResult: result => setVisionMessage(
      result === "pinned" ? "This laptop's camera is set to another classroom. Remove CUES_STATION_ID from the root .env." :
      result === "unavailable" ? "Couldn't link this laptop's camera. Check that the vision service is running and allows this dashboard." : "")});
  }, [client, station, visionStationConfigEnabled]);
  useEffect(() => {
    if (!client || !resolvesStation) return;
    let disposed = false;
    let latest = 0;
    const signedOut = { id: null, message: "Sign in to manage activities" };
    const resolve = async (signedIn: boolean) => {
      const mine = ++latest;
      if (!signedIn) {
        setDefaultStation(signedOut);
        return;
      }
      try {
        const found = await resolveDefaultStation(client);
        if (!disposed && mine === latest)
          setDefaultStation({ id: found.id, message: "" });
      } catch (cause) {
        if (disposed || mine !== latest) return;
        setDefaultStation(
          cause instanceof StationSignInRequired
            ? signedOut
            : {
                id: null,
                message:
                  cause instanceof Error
                    ? cause.message
                    : "Your classroom camera could not be loaded.",
              },
        );
      }
    };
    const initial = latest;
    void client.auth.getSession().then(({ data }) => {
      if (disposed || latest !== initial) return;
      if (data.session)
        setDefaultStation({
          id: null,
          message: "Finding your classroom camera…",
        });
      void resolve(Boolean(data.session));
    });
    const { data } = client.auth.onAuthStateChange((event, session) => {
      if (event === "INITIAL_SESSION" || event === "TOKEN_REFRESHED") return;
      ++latest; // Immediately invalidate in-flight work for the previous identity.
      // A different account: never keep the previous teacher's station on screen.
      setDefaultStation(
        session
          ? { id: null, message: "Finding your classroom camera…" }
          : signedOut,
      );
      // Defer: Supabase calls inside this callback can deadlock the auth lock.
      setTimeout(() => { if (!disposed) void resolve(Boolean(session)); }, 0);
    });
    return () => {
      disposed = true;
      data.subscription.unsubscribe();
    };
  }, [client, resolvesStation]);
  const shownStation = useRef(station);
  useEffect(() => {
    // Another station (account switch, sign-out): drop the old station's rows now.
    if (shownStation.current === station) return;
    shownStation.current = station;
    queueMicrotask(() => {
      setFeed(INITIAL);
      setReviews(reviewsEnabled ? INITIAL_REVIEWS : DISABLED_REVIEWS);
    });
  }, [station, reviewsEnabled]);
  useEffect(() => {
    if (!client) return;
    const subscription = watchDashboard(
      client,
      (state) => {
        if (personObservationsEnabled)
          setFeed((previous) => ({
            ...state,
            snapshot: station ? state.snapshot ?? previous.snapshot : null,
          }));
        else setFeed(state);
      },
      personObservationsEnabled,
      station,
      liveProgressEnabled,
    );
    const offline = () => subscription.disconnect();
    const online = () => setAttempt((n) => n + 1);
    window.addEventListener("offline", offline);
    window.addEventListener("online", online);
    return () => {
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", online);
      subscription.dispose();
    };
  }, [attempt, client, personObservationsEnabled, station, liveProgressEnabled]);
  useEffect(() => {
    if (!client) return;
    const subscription = watchTeacherReviews(
      client,
      (state) =>
        setReviews({
          ...state,
          reviews:
            state.reviews?.filter(
              (review) => !resolvedReviewIds.current.has(review.id),
            ) ?? null,
        }),
      reviewsEnabled,
      station,
    );
    const offline = () => subscription.disconnect();
    const online = () => setReviewAttempt((n) => n + 1);
    window.addEventListener("offline", offline);
    window.addEventListener("online", online);
    return () => {
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", online);
      subscription.dispose();
    };
  }, [client, reviewsEnabled, reviewAttempt, station]);
  useEffect(() => {
    if (selectedId || selectedReviewId) detailsHeading.current?.focus();
  }, [selectedId, selectedReviewId]);

  // People are labelled as the backend names them (seats.display_name,
  // "Person 1", "Person 2"…): no made-up names.
  const seats = feed.snapshot ? seatViews(feed.snapshot) : [];
  const reviewActivity = (id: string) =>
    activityLabel(
      id,
      feed.snapshot?.activities.find((item) => item.id === id)?.name,
    );
  const reviewName = (seatId: string) =>
    seats.find((seat) => seat.id === seatId)?.display_name ?? seatId;
  const observationOptions: ObservationOptions = {
    enabled: personObservationsEnabled,
    now: observationNow,
    connected: feed.connection === "connected" && !feed.error,
  };
  const selected = seats.find((seat) => seat.id === selectedId);
  const hasCurrentTaskObservations =
    !personObservationsEnabled ||
    seats.some(
      (seat) =>
        observationPresentation(seat.state, observationOptions)
          .currentStatus !== null,
    );
  const queue = reviews.reviews ?? [];
  const reviewGroups = groupReviewsBySeat(queue);
  const countStatus = (status: string) =>
    feed.snapshot && hasCurrentTaskObservations
      ? seats.filter(
          (seat) =>
            observationPresentation(seat.state, observationOptions)
              .currentStatus === status,
        ).length
      : "—";
  // People come from the camera: only those it sees right now are listed.
  const inView = seats.filter((seat) =>
    inCameraView(seat.state, observationOptions),
  );
  const cameraReporting = seats.some((seat) =>
    isFresh(seat.state, observationOptions),
  );
  // With no live connection we can't tell whether the camera is on.
  const cameraOffMessage = observationOptions.connected
    ? "The camera is off. People appear here when your classroom camera sees them."
    : "Updates paused. Reconnecting…";
  const peopleCount = feed.snapshot ? inView.length : "—";
  const workingCount = countStatus("in_progress");
  const completedCount = countStatus("done");
  const reviewCount =
    reviews.reviews && !reviews.error && reviews.connection === "connected"
      ? queue.length
      : "—";
  const selectedReview = queue.find((item) => item.id === selectedReviewId);
  const activityNames = [
    ...new Set(
      seats
        .filter((seat) => seat.state?.activity_id)
        .map((seat) => seat.activity),
    ),
  ];
  const observationActivity = !feed.snapshot
    ? "Activity unavailable"
    : activityNames.length > 1
      ? "Multiple activities"
      : (activityNames[0] ?? "No activity assigned");
  const activity = sessionControlsEnabled
    ? sessionActivity
    : observationActivity;
  const selectSeat = (seat: SeatView, opener: HTMLButtonElement) => {
    detailOpener.current = opener;
    setSelectedReviewId(null);
    setSelectedId(seat.id);
  };
  const closeReview = () => {
    setSelectedReviewId(null);
    requestAnimationFrame(() => {
      const opener = document.getElementById(`review-${selectedReviewId}`);
      if (opener instanceof HTMLButtonElement) opener.focus();
      else attentionHeading.current?.focus();
    });
  };
  const closeDetails = () => {
    setSelectedId(null);
    const opener = detailOpener.current;
    if (opener?.isConnected) opener.focus();
    else if (selectedId) seatButtons.current.get(selectedId)?.focus();
  };

  // Session controls sit in the toolbar (main, PR #48); the popover is only
  // the fallback when they are not connected.
  // Live session controls get their own row in the room view; the
  // not-connected fallback stays a small pill in the header.
  const sessionLive = Boolean(sessionControlsEnabled && client);
  const activityPopover =
    sessionLive && client ? (
      <section className="session-toolbar" aria-label="Session controls">
        <SessionControls
          client={client}
          station={station}
          stationMessage={visionMessage || (resolvesStation ? defaultStation.message : undefined)}
          onActivity={setSessionActivity}
          teacherLoginEnabled={teacherLoginEnabled}
        />
      </section>
    ) : (
      <details className="activity-popover">
        <summary>
          Session controls
          <WorkspaceIcon name="chevronDown" />
        </summary>
        <div className="activity-popover-body">
          <p>Session controls are not connected in this environment.</p>
        </div>
      </details>
    );
  const roomPeople: RoomPerson[] = inView.map((seat) => {
    const presentation = observationPresentation(
      seat.state,
      observationOptions,
    );
    return {
      id: seat.id,
      name: seat.display_name,
      status: presentation.label,
      tone: statusTone(presentation),
      activity: seat.activity,
      selected: selected?.id === seat.id,
    };
  });
  const next = nextUp({
    reviews: reviewGroups.map((group) => ({
      name: reviewName(group.seat_id),
      activity: reviewActivity(group.reviews[0].activity_id),
      count: group.reviews.length,
      elevated: group.elevated,
    })),
    flagged: inView
      .filter(
        (seat) =>
          observationPresentation(seat.state, observationOptions).needsReview,
      )
      .map((seat) => ({ name: seat.display_name, activity: seat.activity })),
    inView: inView.length,
    cameraReporting,
  });
  const openNext = () => {
    detailOpener.current =
      document.activeElement instanceof HTMLButtonElement
        ? document.activeElement
        : null;
    const lead = reviewGroups[0];
    if (lead) {
      setSelectedId(null);
      setSelectedReviewId(lead.reviews[0].id);
    } else {
      const seat = inView.find(
        (item) =>
          observationPresentation(item.state, observationOptions).needsReview,
      );
      if (!seat) return;
      setSelectedReviewId(null);
      setSelectedId(seat.id);
    }
    setDrawerOpen(true);
  };
  // Closing returns focus to whatever opened the drawer: a person in the room,
  // the next-up card, or the toggle.
  const closeDrawer = () => {
    setDrawerOpen(false);
    setSelectedId(null);
    setSelectedReviewId(null);
    const opener = detailOpener.current;
    requestAnimationFrame(() =>
      (opener?.isConnected ? opener : drawerToggle.current)?.focus(),
    );
  };
  // Details opened from the room or the next-up card close the whole drawer;
  // ones opened from the drawer's own lists go back to those lists.
  const closeInDrawer = (inside: () => void) => {
    if (detailOpener.current?.closest(".room-drawer")) inside();
    else closeDrawer();
  };
  const timelineMarks = queue.map((review) => ({
    id: review.id,
    at: review.created_at,
    label: `${reviewName(review.seat_id)} flagged`,
  }));

  return (
    <div className="dashboard-shell">
      <WorkspaceSidebar
        accountEnabled={teacherLoginEnabled}
        themeToggle={themeToggleEnabled}
        liveView={liveViewEnabled}
      />
      <main id="main-content" className="dashboard-main">
        {roomViewEnabled ? (
          <>
            <header className="room-header">
              <div>
                <h1>your classroom</h1>
                <p className="room-subtitle">{activity}</p>
              </div>
              <div className="room-actions">
                {sessionLive ? null : activityPopover}
                <button
                  type="button"
                  className="room-details-toggle"
                  aria-expanded={drawerOpen}
                  aria-controls="room-drawer"
                  ref={drawerToggle}
                  onClick={() => {
                    detailOpener.current = drawerToggle.current;
                    setDrawerOpen(true);
                    requestAnimationFrame(() => drawerClose.current?.focus());
                  }}
                >
                  <WorkspaceIcon name="camera" />
                  Camera and details
                </button>
              </div>
            </header>
            {sessionLive ? (
              <div className="room-session">{activityPopover}</div>
            ) : null}
          </>
        ) : (
          <>
            <div className="ws-hero">
              <span className="ws-grain" aria-hidden="true" />
              <header className="page-intro">
                <div>
                  <h1>your classroom</h1>
                  <p>A clear view of who’s ready and who needs a hand.</p>
                </div>
                <button
                  className="refresh-button"
                  type="button"
                  onClick={() => {
                    setAttempt((n) => n + 1);
                    setReviewAttempt((n) => n + 1);
                  }}
                  disabled={!client || feed.loading}
                >
                  <WorkspaceIcon name="refresh" />
                  {feed.loading && client ? "Refreshing…" : "Refresh"}
                </button>
              </header>
              <section
                className="classroom-summary"
                aria-label="Classroom summary"
              >
                <dl className="overview-metrics">
                  <div>
                    <dd>{peopleCount}</dd>
                    <dt>People in view</dt>
                  </div>
                  <div>
                    <dd>{workingCount}</dd>
                    <dt>In progress</dt>
                  </div>
                  <div>
                    <dd>{completedCount}</dd>
                    <dt>Completed</dt>
                  </div>
                  <div>
                    <dd>{reviewCount}</dd>
                    <dt>Pending reviews</dt>
                  </div>
                </dl>
              </section>
            </div>
            <div className="workspace-toolbar">
              <div className="current-activity">
                <span className="toolbar-label">Current activity</span>
                <strong>{activity}</strong>
              </div>
              {activityPopover}
            </div>
          </>
        )}
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
        {roomViewEnabled ? (
          <>
            <div className="room-layout">
              <ClassroomRoom
                people={roomPeople}
                emptyMessage={
                  !feed.snapshot
                    ? "Loading the room…"
                    : cameraReporting
                      ? "No one is in view right now."
                      : cameraOffMessage
                }
                onSelect={(id, opener) => {
                  const seat = seats.find((item) => item.id === id);
                  if (!seat) return;
                  selectSeat(seat, opener);
                  setDrawerOpen(true);
                }}
              />
              <NextUpCard
                next={next}
                summary={
                  typeof peopleCount === "number" &&
                  typeof workingCount === "number" &&
                  typeof completedCount === "number"
                    ? `${peopleCount} in view · ${workingCount} working · ${completedCount} finished`
                    : undefined
                }
                onOpen={openNext}
              />
            </div>
            <LessonTimeline marks={timelineMarks} />
            <div
              id="room-drawer"
              className="room-drawer"
              data-open={drawerOpen || undefined}
              inert={!drawerOpen}
              onKeyDown={(event) => {
                if (event.key === "Escape" && !selectedId && !selectedReviewId)
                  closeDrawer();
              }}
            >
              <div className="room-drawer-head">
                <h2>Camera and details</h2>
                <button
                  type="button"
                  className="text-button"
                  ref={drawerClose}
                  onClick={closeDrawer}
                >
                  Close
                </button>
              </div>
              <div className="monitor-workspace">
                <div className="monitor-main">
                  <LocalClassroomFeed activity={activity} />
                </div>
                <Card
                  role="complementary"
                  className="attention-panel"
                  id="attention-panel"
                  aria-label={
                    selectedReviewId
                      ? "Review details"
                      : selected
                        ? "Seat details"
                        : "Teacher reviews"
                  }
                >
                  {selectedReviewId ? (
                    <TeacherReviewDetails
                      review={selectedReview}
                      seats={seats}
                      activities={feed.snapshot?.activities ?? []}
                      stale={
                        !!reviews.error || reviews.connection === "disconnected"
                      }
                      close={() => closeInDrawer(closeReview)}
                      headingRef={detailsHeading}
                    >
                      {reviewActionsEnabled && client && selectedReview ? (
                        <TeacherReviewActions
                          key={selectedReviewId}
                          client={client}
                          review={selectedReview}
                          onResolved={(resolved) => {
                            resolvedReviewIds.current.add(resolved.id);
                            setReviews((state) => ({
                              ...state,
                              reviews:
                                state.reviews?.filter(
                                  (item) => item.id !== resolved.id,
                                ) ?? null,
                            }));
                          }}
                        />
                      ) : null}
                    </TeacherReviewDetails>
                  ) : selected ? (
                    <SeatDetails
                      seat={selected}
                      observationOptions={observationOptions}
                      close={() => closeInDrawer(closeDetails)}
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
                          <WorkspaceIcon name="review" />
                          Teacher reviews
                        </h2>
                        <span
                          className={
                            queue.length
                              ? "attention-count has-items"
                              : "attention-count"
                          }
                        >
                          {typeof reviewCount === "number"
                            ? `${reviewCount} pending`
                            : "Not connected"}
                        </span>
                      </header>
                      {!reviewsEnabled || configurationError ? (
                        <div className="queue-empty">
                          <p>Teacher reviews not connected</p>
                          <span>
                            Pending reviews will appear here when the review
                            data source is available.
                          </span>
                        </div>
                      ) : (
                        <>
                          {reviews.error ||
                          reviews.connection === "disconnected" ? (
                            <div className="review-feed-notice" role="alert">
                              <p>
                                {reviews.error ??
                                  "Live review updates are disconnected."}
                              </p>
                              {reviews.reviews ? (
                                <p>
                                  Showing the last loaded reviews. Resolved
                                  items may still appear.
                                </p>
                              ) : null}
                              <button
                                type="button"
                                disabled={reviews.loading}
                                onClick={() => setReviewAttempt((n) => n + 1)}
                              >
                                Retry reviews
                              </button>
                            </div>
                          ) : null}
                          {queue.length ? (
                            <ul className="attention-list">
                              {reviewGroups.map((group) => {
                                const lead = group.reviews[0];
                                const tasks = new Set(
                                  group.reviews.map(
                                    (review) => review.activity_id,
                                  ),
                                );
                                return (
                                  <li key={group.seat_id}>
                                    <button
                                      type="button"
                                      className="review-entry"
                                      id={`review-${lead.id}`}
                                      onClick={(event) => {
                                        detailOpener.current =
                                          event.currentTarget;
                                        setSelectedId(null);
                                        setSelectedReviewId(lead.id);
                                      }}
                                    >
                                      <ReviewRowContent
                                        name={reviewName(group.seat_id)}
                                        meta={`${
                                          tasks.size > 1
                                            ? `${tasks.size} tasks`
                                            : reviewActivity(lead.activity_id)
                                        }${
                                          group.reviews.length > 1
                                            ? ` · ${group.reviews.length} reviews`
                                            : ""
                                        }`}
                                        time={group.latest}
                                        elevated={group.elevated}
                                      />
                                      <span className="sr-only">
                                        View review
                                      </span>
                                    </button>
                                  </li>
                                );
                              })}
                            </ul>
                          ) : !reviews.error &&
                            reviews.connection !== "disconnected" ? (
                            <div className="queue-empty" role="status">
                              <p>
                                {reviews.reviews === null
                                  ? "Loading teacher reviews…"
                                  : "No pending teacher reviews"}
                              </p>
                              <span>
                                {reviews.reviews === null
                                  ? "Checking the review queue."
                                  : "New pending reviews will appear here automatically."}
                              </span>
                            </div>
                          ) : null}
                        </>
                      )}
                    </section>
                  )}
                </Card>
              </div>
            </div>
            {drawerOpen ? (
              <button
                type="button"
                className="room-scrim"
                aria-label="Close camera and details"
                onClick={closeDrawer}
              />
            ) : null}
          </>
        ) : (
          <>
            <div className="monitor-workspace">
              <div className="monitor-main">
                <LocalClassroomFeed activity={activity} />
                <section
                  className="seat-strip people-card"
                  aria-labelledby="seats-heading"
                >
                  <header className="strip-heading">
                    <h2 id="seats-heading">People</h2>
                  </header>
                  {!feed.snapshot ? (
                    <p className="strip-empty" role="status">
                      {feed.loading && !configurationError
                        ? "Loading observations…"
                        : "Seat observations unavailable"}
                    </p>
                  ) : inView.length === 0 ? (
                    <p className="strip-empty" role="status">
                      {cameraReporting
                        ? "No one is in view right now."
                        : cameraOffMessage}
                    </p>
                  ) : (
                    <div className="seat-items">
                      {inView.map((seat) => {
                        const presentation = observationPresentation(
                          seat.state,
                          observationOptions,
                        );
                        return (
                          <button
                            className={`seat-item is-${statusTone(presentation)} ${presentation.needsReview ? "needs-review" : ""} ${selected?.id === seat.id ? "is-selected" : ""}`}
                            key={seat.id}
                            ref={(node) => {
                              if (node) seatButtons.current.set(seat.id, node);
                              else seatButtons.current.delete(seat.id);
                            }}
                            type="button"
                            aria-pressed={selected?.id === seat.id}
                            onClick={(event) =>
                              selectSeat(seat, event.currentTarget)
                            }
                          >
                            <PersonRowContent
                              name={seat.display_name}
                              status={presentation.label}
                              icon={statusIcon(presentation)}
                              activity={seat.activity}
                            />
                          </button>
                        );
                      })}
                    </div>
                  )}
                </section>
              </div>
              <Card
                role="complementary"
                className="attention-panel"
                id="attention-panel"
                aria-label={
                  selectedReviewId
                    ? "Review details"
                    : selected
                      ? "Seat details"
                      : "Teacher reviews"
                }
              >
                {selectedReviewId ? (
                  <TeacherReviewDetails
                    review={selectedReview}
                    seats={seats}
                    activities={feed.snapshot?.activities ?? []}
                    stale={
                      !!reviews.error || reviews.connection === "disconnected"
                    }
                    close={closeReview}
                    headingRef={detailsHeading}
                  >
                    {reviewActionsEnabled && client && selectedReview ? (
                      <TeacherReviewActions
                        key={selectedReviewId}
                        client={client}
                        review={selectedReview}
                        onResolved={(resolved) => {
                          resolvedReviewIds.current.add(resolved.id);
                          setReviews((state) => ({
                            ...state,
                            reviews:
                              state.reviews?.filter(
                                (item) => item.id !== resolved.id,
                              ) ?? null,
                          }));
                        }}
                      />
                    ) : null}
                  </TeacherReviewDetails>
                ) : selected ? (
                  <SeatDetails
                    seat={selected}
                    observationOptions={observationOptions}
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
                        <WorkspaceIcon name="review" />
                        Teacher reviews
                      </h2>
                      <span
                        className={
                          queue.length
                            ? "attention-count has-items"
                            : "attention-count"
                        }
                      >
                        {typeof reviewCount === "number"
                          ? `${reviewCount} pending`
                          : "Not connected"}
                      </span>
                    </header>
                    {!reviewsEnabled || configurationError ? (
                      <div className="queue-empty">
                        <p>Teacher reviews not connected</p>
                        <span>
                          Pending reviews will appear here when the review data
                          source is available.
                        </span>
                      </div>
                    ) : (
                      <>
                        {reviews.error ||
                        reviews.connection === "disconnected" ? (
                          <div className="review-feed-notice" role="alert">
                            <p>
                              {reviews.error ??
                                "Live review updates are disconnected."}
                            </p>
                            {reviews.reviews ? (
                              <p>
                                Showing the last loaded reviews. Resolved items
                                may still appear.
                              </p>
                            ) : null}
                            <button
                              type="button"
                              disabled={reviews.loading}
                              onClick={() => setReviewAttempt((n) => n + 1)}
                            >
                              Retry reviews
                            </button>
                          </div>
                        ) : null}
                        {queue.length ? (
                          <ul className="attention-list">
                            {reviewGroups.map((group) => {
                              const lead = group.reviews[0];
                              const tasks = new Set(
                                group.reviews.map(
                                  (review) => review.activity_id,
                                ),
                              );
                              return (
                                <li key={group.seat_id}>
                                  <button
                                    type="button"
                                    className="review-entry"
                                    id={`review-${lead.id}`}
                                    onClick={() => {
                                      setSelectedId(null);
                                      setSelectedReviewId(lead.id);
                                    }}
                                  >
                                    <ReviewRowContent
                                      name={reviewName(group.seat_id)}
                                      meta={`${
                                        tasks.size > 1
                                          ? `${tasks.size} tasks`
                                          : reviewActivity(lead.activity_id)
                                      }${
                                        group.reviews.length > 1
                                          ? ` · ${group.reviews.length} reviews`
                                          : ""
                                      }`}
                                      time={group.latest}
                                      elevated={group.elevated}
                                    />
                                    <span className="sr-only">View review</span>
                                  </button>
                                </li>
                              );
                            })}
                          </ul>
                        ) : !reviews.error &&
                          reviews.connection !== "disconnected" ? (
                          <div className="queue-empty" role="status">
                            <p>
                              {reviews.reviews === null
                                ? "Loading teacher reviews…"
                                : "No pending teacher reviews"}
                            </p>
                            <span>
                              {reviews.reviews === null
                                ? "Checking the review queue."
                                : "New pending reviews will appear here automatically."}
                            </span>
                          </div>
                        ) : null}
                      </>
                    )}
                  </section>
                )}
              </Card>
            </div>
          </>
        )}
        <footer className="workspace-footer">
          <span>
            Student camera images and video stay on the classroom laptop.
          </span>
          <span>
            {sessionControlsEnabled
              ? "Session controls use your camera's saved state."
              : "Session controls are not connected."}
          </span>
        </footer>
      </main>
    </div>
  );
}
