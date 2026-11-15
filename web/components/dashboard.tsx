"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import { seatViews, type SeatView } from "@/lib/dashboard";
import {
  INITIAL_REVIEWS,
  DISABLED_REVIEWS,
  watchTeacherReviews,
  type ReviewFeedState,
} from "@/lib/teacher-review-feed";
import {
  groupReviewsBySeat,
  type TeacherReview,
} from "@/lib/teacher-reviews";
import { watchDashboard, type FeedState } from "@/lib/dashboard-feed";
import {
  resolveDefaultStation,
  StationSignInRequired,
} from "@/lib/default-station";
import { createDashboardClient } from "@/lib/supabase";
import { startLocalVisionSync } from "@/lib/local-vision";
import { SessionControls } from "@/components/session-controls";
import LocalClassroomFeed from "@/components/local-classroom-feed";
import { PersonDetails } from "@/components/person-panel";
import { MarkReviewedButton } from "@/components/mark-reviewed-button";
import {
  CAMERA_CONFLICT_MESSAGE,
  cameraConflict,
  readStationWriter,
} from "@/lib/station-writer";
import {
  inCameraView,
  isFresh,
  observationPresentation,
  type ObservationOptions,
} from "@/lib/observation-presentation";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { WorkspaceIcon } from "@/components/workspace-icon";
import {
  PersonRowContent,
  ReviewRowContent,
  type PersonTone,
} from "@/components/workspace-rows";

// The companion is decorative and only shown signed out: load it on demand.
const Companion = dynamic(() => import("@/components/login-companion"), {
  ssr: false,
});

const ignoreActivity = () => {};
const INITIAL: FeedState = {
  snapshot: null,
  connection: "connecting",
  loading: true,
  error: null,
};
type Presentation = ReturnType<typeof observationPresentation>;
const statusTone = (presentation: Presentation): PersonTone =>
  presentation.needsReview
    ? "review"
    : presentation.currentStatus === "done"
      ? "done"
      : presentation.currentStatus === "in_progress"
        ? "working"
        : "quiet";

/** Who the dashboard is for: unknown until the sign-in check returns. */
type Account =
  | { state: "checking" }
  | { state: "signed-out" }
  | { state: "finding" }
  | { state: "ready"; station: string }
  | { state: "error"; message: string };

/** The signed-out classroom: one calm question, as on the sign-in page. */
function SignInCard() {
  return (
    <section className="ws-signin" aria-labelledby="signin-heading">
      <Companion size={96} />
      <h1 id="signin-heading">Sign in to see your classroom</h1>
      <p>Cues shows the people your classroom camera sees and who needs you.</p>
      <Link className="ws-pill is-dark" href="/login">
        Sign in
        <WorkspaceIcon name="arrow" />
      </Link>
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
  themeToggleEnabled = false,
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
  themeToggleEnabled?: boolean;
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
  const [feed, setFeed] = useState<FeedState>(INITIAL);
  const [attempt, setAttempt] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const listHeading = useRef<HTMLHeadingElement>(null);
  const [reviews, setReviews] = useState<ReviewFeedState>(
    reviewsEnabled ? INITIAL_REVIEWS : DISABLED_REVIEWS,
  );
  const resolvedReviewIds = useRef(new Set<string>());
  const [reviewAttempt, setReviewAttempt] = useState(0);
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
  const [visionMessage, setVisionMessage] = useState("");
  // Tell this laptop's vision service the signed-in teacher's resolved station.
  useEffect(() => {
    if (!visionStationConfigEnabled || !client || !station) return;
    return startLocalVisionSync(client, station, {
      onResult: (result) =>
        setVisionMessage(
          result === "pinned"
            ? "This laptop’s camera is set to another classroom. Remove CUES_STATION_ID from the root .env."
            : result === "unavailable"
              ? "Couldn’t link this laptop’s camera. Check that the vision service is running."
              : "",
        ),
    });
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
    void client.auth.getSession().then(({ data }) => {
      if (disposed || latest !== initial) return;
      void resolve(Boolean(data.session));
    });
    const { data } = client.auth.onAuthStateChange((event, session) => {
      if (event === "INITIAL_SESSION" || event === "TOKEN_REFRESHED") return;
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
  const shownStation = useRef(station);
  useEffect(() => {
    // Another station (account switch, sign-out): drop the old station's rows now.
    if (shownStation.current === station) return;
    shownStation.current = station;
    queueMicrotask(() => {
      setFeed(INITIAL);
      setSelectedId(null);
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
            snapshot: station ? (state.snapshot ?? previous.snapshot) : null,
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

  const signedOut =
    teacherLoginEnabled && resolvesStation && account.state === "signed-out";
  // Without a station there is nothing to load yet: say why, not "error".
  const waitingForStation = resolvesStation && !station;

  // People are labelled as the backend names them (seats.display_name,
  // "Person 1", "Person 2"…): no made-up names.
  const seats = feed.snapshot ? seatViews(feed.snapshot) : [];
  const nameOf = (seatId: string) =>
    seats.find((seat) => seat.id === seatId)?.display_name ?? "A student";
  const observationOptions: ObservationOptions = {
    enabled: personObservationsEnabled,
    now: observationNow,
    connected: feed.connection === "connected" && !feed.error,
  };
  const present = (seat: SeatView) =>
    observationPresentation(seat.state, observationOptions);
  const queue = reviews.reviews ?? [];
  const reviewGroups = groupReviewsBySeat(queue);
  const reviewsFor = (seatId: string): TeacherReview[] =>
    reviewGroups.find((group) => group.seat_id === seatId)?.reviews ?? [];
  // People come from the camera: only those it sees right now are listed.
  const inView = seats.filter((seat) =>
    inCameraView(seat.state, observationOptions),
  );
  const cameraReporting = seats.some((seat) =>
    isFresh(seat.state, observationOptions),
  );
  const reviewsLive =
    reviewsEnabled &&
    !configurationError &&
    reviews.reviews !== null &&
    !reviews.error &&
    reviews.connection === "connected";
  const activityNames = [
    ...new Set(
      seats.filter((seat) => seat.state?.activity_id).map((s) => s.activity),
    ),
  ];
  // Each row names its task only when the class is on more than one.
  const mixedActivities = activityNames.length > 1;
  const observationActivity = !feed.snapshot
    ? "Waiting for the camera"
    : activityNames.length > 1
      ? "Several activities"
      : (activityNames[0] ?? "No activity yet");
  const sessionLive = Boolean(sessionControlsEnabled && client);
  // One camera per station: while a second camera is being refused (and paused), say so.
  const [conflict, setConflict] = useState(false);
  useEffect(() => {
    if (!client || !station || !sessionControlsEnabled) return;
    let disposed = false;
    const check = () => {
      void readStationWriter(client, station)
        .then((writer) => {
          if (!disposed) setConflict(cameraConflict(writer, Date.now()));
        })
        .catch(() => {
          if (!disposed) setConflict(false);
        });
    };
    check();
    const timer = setInterval(check, 5000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [client, station, sessionControlsEnabled]);
  // With session controls, the activity picker itself shows the activity.
  const activity = observationActivity;

  // One list: whoever Cues asked about first (even out of view), then
  // everyone else the camera sees, left to right.
  const others = inView.filter((seat) => reviewsFor(seat.id).length === 0);
  const closeDetails = () => {
    const id = selectedId;
    setSelectedId(null);
    requestAnimationFrame(() =>
      (id
        ? document.querySelector<HTMLButtonElement>(`[aria-controls="more-${id}"]`)
        : listHeading.current
      )?.focus(),
    );
  };
  const resolved = (review: TeacherReview) => {
    resolvedReviewIds.current.add(review.id);
    setReviews((state) => ({
      ...state,
      reviews: state.reviews?.filter((item) => item.id !== review.id) ?? null,
    }));
  };
  // "Mark as reviewed": close this person's review requests here at once (every page reads
  // the same table, so they leave the others too) and let vision reset them to working.
  const markReviewedButton = (sessionId: string | null, seatId: string) =>
    reviewActionsEnabled && client && sessionId ? (
      <MarkReviewedButton
        key={seatId}
        client={client}
        sessionId={sessionId}
        seatId={seatId}
        onMarked={(marked) =>
          setReviews((state) => {
            const closed = (state.reviews ?? []).filter(
              (item) => item.seat_id === marked,
            );
            for (const item of closed) resolvedReviewIds.current.add(item.id);
            return {
              ...state,
              reviews:
                state.reviews?.filter((item) => item.seat_id !== marked) ?? null,
            };
          })
        }
      />
    ) : null;
  const row = (
    seatId: string,
    content: React.ReactNode,
    presentation: Presentation | null,
    pending: readonly TeacherReview[],
  ) => {
    const open = selectedId === seatId;
    return (
      <li key={seatId} className={open ? "is-open" : undefined}>
        <button
          type="button"
          className="ws-row"
          aria-expanded={open}
          aria-controls={`more-${seatId}`}
          onClick={() => setSelectedId(open ? null : seatId)}
        >
          {content}
        </button>
        {open ? (
          <PersonDetails
            id={`more-${seatId}`}
            presentation={presentation}
            reviews={pending}
            stale={!!reviews.error || reviews.connection === "disconnected"}
            client={reviewActionsEnabled ? client : null}
            onResolved={resolved}
            actions={markReviewedButton(
              pending[0]?.session_id ??
                seats.find((seat) => seat.id === seatId)?.state?.session_id ??
                null,
              seatId,
            )}
          />
        ) : null}
      </li>
    );
  };

  const peopleEmpty = !feed.snapshot
    ? waitingForStation
      ? account.state === "error"
        ? account.message
        : "Finding your classroom…"
      : feed.loading && !configurationError
        ? "Loading…"
        : "People aren’t available right now."
    : cameraReporting
      ? "No one is in view right now."
      : observationOptions.connected
        ? "The camera is off. People appear here when it sees them."
        : "Updates paused. Reconnecting…";

  const connectionProblem =
    !waitingForStation &&
    (configurationError || feed.error || feed.connection === "disconnected");

  return (
    <div className="dashboard-shell">
      <WorkspaceSidebar
        accountEnabled={teacherLoginEnabled}
        themeToggle={themeToggleEnabled}
      />
      <main id="main-content" className="dashboard-main">
        {signedOut ? (
          <SignInCard />
        ) : (
          <>
            <section className="ws-hero" aria-labelledby="classroom-heading">
              <header className="page-intro">
                <div>
                  <h1 id="classroom-heading">your classroom</h1>
                  {sessionLive ? null : (
                    <p className="ws-subtitle">{activity}</p>
                  )}
                </div>
              </header>
              {sessionLive && client ? (
                <SessionControls
                  client={client}
                  station={station}
                  stationMessage={
                    visionMessage ||
                    (account.state === "error" ? account.message : undefined)
                  }
                  onActivity={ignoreActivity}
                  teacherLoginEnabled={teacherLoginEnabled}
                />
              ) : null}
              {sessionLive && conflict ? (
                <p className="station-busy" role="status">
                  {CAMERA_CONFLICT_MESSAGE}
                </p>
              ) : null}
            </section>

            {connectionProblem ? (
              <section className="notice" role="alert">
                <p>
                  {configurationError
                    ? "Cues isn’t connected to your classroom data here."
                    : feed.snapshot
                      ? "Live updates paused. Showing the last update."
                      : "Couldn’t load your classroom."}
                </p>
                {!configurationError ? (
                  <button
                    type="button"
                    className="ws-pill"
                    disabled={feed.loading}
                    onClick={() => setAttempt((n) => n + 1)}
                  >
                    Try again
                  </button>
                ) : null}
              </section>
            ) : null}

            <div className="monitor-workspace">
              <LocalClassroomFeed />
              <section
                className="ws-panel class-panel"
                aria-labelledby="class-heading"
                onKeyDown={(event) => {
                  if (event.key === "Escape" && selectedId) closeDetails();
                }}
              >
                <header className="panel-heading">
                  <h2 id="class-heading" ref={listHeading} tabIndex={-1}>
                    Class
                  </h2>
                  {reviewsLive && reviewGroups.length ? (
                    <span className="ws-count">
                      {reviewGroups.length}
                      <span className="sr-only"> need you</span>
                    </span>
                  ) : null}
                </header>

                {reviewsEnabled &&
                !configurationError &&
                (reviews.error || reviews.connection === "disconnected") ? (
                  <div className="list-notice" role="alert">
                    <p>Couldn’t check for new requests.</p>
                    <button
                      type="button"
                      className="ws-pill"
                      disabled={reviews.loading}
                      onClick={() => setReviewAttempt((n) => n + 1)}
                    >
                      Try again
                    </button>
                  </div>
                ) : null}

                {reviewGroups.length ? (
                  <>
                    <p className="list-label">Needs you</p>
                    <ul className="row-list">
                      {reviewGroups.map((group) => {
                        const seat = seats.find((s) => s.id === group.seat_id);
                        const visible = inView.some((s) => s.id === group.seat_id);
                        return row(
                          group.seat_id,
                          <ReviewRowContent
                            name={nameOf(group.seat_id)}
                            meta={
                              !visible
                                ? "Not in view"
                                : mixedActivities && seat
                                  ? seat.activity
                                  : ""
                            }
                            time={group.latest}
                            elevated={group.elevated}
                          />,
                          visible && seat ? present(seat) : null,
                          group.reviews,
                        );
                      })}
                    </ul>
                  </>
                ) : reviewsLive ? (
                  <p className="list-clear" role="status">
                    All clear. Cues will ask when someone may need you.
                  </p>
                ) : null}

                {others.length ? (
                  <>
                    {reviewGroups.length ? (
                      <p className="list-label">Everyone else</p>
                    ) : null}
                    <ul className="row-list">
                      {others.map((seat) => {
                        const presentation = present(seat);
                        return row(
                          seat.id,
                          <PersonRowContent
                            name={seat.display_name}
                            status={presentation.label}
                            tone={statusTone(presentation)}
                            activity={mixedActivities ? seat.activity : ""}
                          />,
                          presentation,
                          [],
                        );
                      })}
                    </ul>
                  </>
                ) : inView.length === 0 ? (
                  <p className="panel-empty" role="status">
                    {peopleEmpty}
                  </p>
                ) : null}
              </section>
            </div>
          </>
        )}

      </main>
    </div>
  );
}
