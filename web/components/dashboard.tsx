"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { seatViews, type SeatView } from "@/lib/dashboard";
import {
  INITIAL_FEED,
  useDashboardFeeds,
} from "@/components/dashboard/use-dashboard-feeds";
import { AttentionList } from "@/components/dashboard/attention-list";
import { ReviewPageList } from "@/components/dashboard/review-page-list";
import { useCompanionCount } from "@/components/dashboard/use-companion-count";
import { useCameraConflict } from "@/components/dashboard/use-camera-conflict";
import { useObservationClock } from "@/components/dashboard/use-observation-clock";
import { useTeacherStation } from "@/components/dashboard/use-teacher-station";
import {
  useDropClearedMarks,
  useSavedMarks,
} from "@/components/dashboard/use-saved-marks";
import {
  INITIAL_REVIEWS,
  DISABLED_REVIEWS,
} from "@/lib/teacher-review-feed";
import {
  activityLabel,
  groupReviewsBySeat,
  type TeacherReview,
} from "@/lib/teacher-reviews";
import type { DashboardFeatures } from "@/lib/dashboard-features";
import { SessionControls } from "@/components/session-controls";
import LocalClassroomFeed from "@/components/local-classroom-feed";
import { PersonDetails } from "@/components/person-panel";
import {
  FlagDecisionButtons,
  MarkReviewedButton,
} from "@/components/mark-reviewed-button";
import { TeacherReviewActions } from "@/components/teacher-review-actions";
import { CameraHealthStrip } from "@/components/camera-health-strip";
import { ReviewCompanion } from "@/components/review-companion";
import { StudentStrip } from "@/components/student-strip";
import {
  reviewQueue,
  stripEntries,
} from "@/lib/classroom-view";
import {
  CAMERA_CONFLICT_MESSAGE,
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
  type PersonTone,
} from "@/components/workspace-rows";

// The companion is decorative and only shown signed out: load it on demand.
const Companion = dynamic(() => import("@/components/login-companion"), {
  ssr: false,
});

const ignoreActivity = () => {};
type Presentation = ReturnType<typeof observationPresentation>;
const statusTone = (presentation: Presentation): PersonTone =>
  presentation.needsReview
    ? "review"
    : presentation.currentStatus === "done"
      ? "done"
      : presentation.currentStatus === "in_progress"
        ? "working"
        : "quiet";

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
  view = "classroom",
  features,
  stationId = "",
  hostedDashboardOrigin = "https://cues.nyc",
}: {
  /** "classroom" (the default) or "review", the To review page. */
  view?: "classroom" | "review";
  /** Every feature flag, resolved on the server (lib/dashboard-features.ts). */
  features: DashboardFeatures;
  /** Explicit dev/test override (CUES_STATION_OVERRIDE). Normally empty: a signed-in
   * teacher's own default station is used. */
  stationId?: string;
  hostedDashboardOrigin?: string;
}) {
  const {
    reviewPageEnabled,
    liveProgressEnabled,
    personObservationsEnabled,
    sessionControlsEnabled,
    reviewsEnabled,
    reviewActionsEnabled,
    teacherLoginEnabled,
    themeToggleEnabled,
    hostedLocalFeedEnabled,
    companionEnabled,
    visionStationConfigEnabled,
    healthStripEnabled,
    interventionsEnabled,
    resetPeopleEnabled,
    reviewWaitingEnabled,
  } = features;
  const observationNow = useObservationClock(personObservationsEnabled);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const listHeading = useRef<HTMLHeadingElement>(null);

  const resolvedReviewIds = useRef(new Set<string>());
  const { client, configurationError, resolvesStation, account, station } =
    useTeacherStation({
      stationId,
      sessionControlsEnabled,
      teacherLoginEnabled,
      reviewActionsEnabled,
      visionStationConfigEnabled,
    });
  const [markedSeats, setMarkedSeats] = useSavedMarks(station);
  const { feed, setFeed, reviews, setReviews, retryFeed, retryReviews } =
    useDashboardFeeds({
    client,
    station,
    personObservationsEnabled,
    liveProgressEnabled,
    reviewsEnabled,
    interventionsEnabled,
    resolvedReviewIds,
  });
  const shownStation = useRef(station);
  useEffect(() => {
    // Another station (account switch, sign-out): drop the old station's rows now.
    if (shownStation.current === station) return;
    shownStation.current = station;
    queueMicrotask(() => {
      setFeed(INITIAL_FEED);
      setSelectedId(null);
      setReviews(reviewsEnabled ? INITIAL_REVIEWS : DISABLED_REVIEWS);
    });
  }, [station, reviewsEnabled, setFeed, setReviews]);

  const signedOut =
    teacherLoginEnabled && resolvesStation && account.state === "signed-out";
  // Without a station there is nothing to load yet: say why, not "error".
  const waitingForStation =
    resolvesStation && !station && !configurationError;

  // People are labelled as the backend names them (seats.display_name,
  // "Person 1", "Person 2"…): no made-up names.
  const seats = feed.snapshot ? seatViews(feed.snapshot) : [];
  const activityName = (id: string) =>
    activityLabel(
      id,
      feed.snapshot?.activities.find((item) => item.id === id)?.name,
    );
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
  const conflict = useCameraConflict(client, station, sessionControlsEnabled);
  // With session controls, the activity picker itself shows the activity.
  const activity = observationActivity;

  // A mark lasts until vision reports the person out of review.
  // Read the raw status, not the on-screen one: a stale or paused observation
  // must not drop the mark before vision has actually reset the person.
  // Null until the seats load, so marks kept from the other page survive.
  const stillFlagged = !feed.snapshot
    ? null
    : seats
    .filter(
      (seat) =>
        markedSeats.has(seat.id) &&
        (seat.state?.status === "review" || seat.state?.status === "needs_help"),
    )
    .map((seat) => seat.id)
    .join(",");
  useDropClearedMarks(stillFlagged, setMarkedSeats);
  // People whose row reads Needs Review but who have no request yet: listed on
  // To review so the two agree. Only once the review feed is live, so no one is
  // shown twice while requests are still loading.
  const { flagged: flaggedOnly, count: waitingCount } = reviewQueue({
    enabled: reviewWaitingEnabled,
    live: reviewsLive,
    people: inView,
    flagged: (seat) => present(seat).needsReview,
    askedSeatIds: reviewGroups.map((group) => group.seat_id),
    marked: markedSeats,
  });
  const { companionCount, forgetLostPeople } = useCompanionCount({
    flaggedOnly,
    waitingCount,
    markedSeats,
    askedSeatIds: reviewGroups.map((group) => group.seat_id),
    seats,
    observationNow,
    reviewsLive,
    reviewWaitingEnabled,
    hasSnapshot: Boolean(feed.snapshot),
  });
  // Attention lists them too (web.review_waiting), under the requests, so the
  // cards and Attention always agree. They stay until the teacher answers.
  const flaggedIdSet = new Set(flaggedOnly.map((seat) => seat.id));
  // Marked as reviewed, but the camera hasn't reset them yet: not "All clear"
  // while their card still reads Needs Review.
  const catchingUp =
    reviewWaitingEnabled &&
    reviewsLive &&
    inView.some(
      (seat) => markedSeats.has(seat.id) && present(seat).needsReview,
    );
  // A person picked from the strip who has no request opens in the side
  // panel; someone with a request opens in place in the attention list.
  // A flagged person opens in place in the attention list too.
  const selectedPerson =
    selectedId &&
    reviewsFor(selectedId).length === 0 &&
    !flaggedIdSet.has(selectedId)
      ? (inView.find((seat) => seat.id === selectedId) ?? null)
      : null;
  // A request arrives for the person open in the side panel: the panel closes
  // and they open in the attention list, so carry focus to their row there.
  const panelPerson = useRef<string | null>(null);
  const panelId = selectedPerson?.id ?? null;
  useEffect(() => {
    const was = panelPerson.current;
    panelPerson.current = panelId;
    if (!was || panelId || selectedId !== was) return;
    if (!document.activeElement || document.activeElement === document.body)
      document
        .querySelector<HTMLButtonElement>(`.row-list [aria-controls="more-${was}"]`)
        ?.focus();
  }, [panelId, selectedId]);
  // Close the open person and return focus to what opened them: the card the
  // teacher pressed Escape on, else their row, else the list heading.
  const closeDetails = (returnTo?: HTMLElement | null) => {
    const id = selectedId;
    setSelectedId(null);
    requestAnimationFrame(() =>
      (returnTo?.isConnected
        ? returnTo
        : id
          ? document.querySelector<HTMLButtonElement>(`[aria-controls="more-${id}"]`)
          : listHeading.current
      )?.focus(),
    );
  };
  // After a decision or a mark: if the person has nothing left to show (no other
  // request and out of view), close their row so it can't reopen on its own later;
  // otherwise keep focus on their row, which may have moved to the other group.
  // The review feed failed or dropped: the notice says so, and no "All clear"
  // or "Checking…" shows under it.
  const reviewNotice =
    reviewsEnabled &&
    !configurationError &&
    Boolean(reviews.error || reviews.connection === "disconnected");
  const pageHeading = useRef<HTMLHeadingElement>(null);
  // Settle in a layout effect after the update that removed the review has
  // committed, so the count is never stale and focus lands before paint.
  const [settling, setSettling] = useState<{ seat: string } | null>(null);
  const settleRow = (seatId: string) => setSettling({ seat: seatId });
  useLayoutEffect(() => {
    if (!settling) return;
    const seatId = settling.seat;
    const remaining =
      reviewGroups.find((group) => group.seat_id === seatId)?.reviews.length ??
      0;
    if (view === "review") {
      // The card stays while the person has another request: keep focus on
      // it; otherwise the page title.
      (remaining
        ? document.getElementById(`review-card-${seatId}`)
        : pageHeading.current
      )?.focus();
      return;
    }
    if (!remaining && !inView.some((seat) => seat.id === seatId)) {
      queueMicrotask(() => setSelectedId(null));
      listHeading.current?.focus();
      return;
    }
    document
      .querySelector<HTMLButtonElement>(`[aria-controls="more-${seatId}"]`)
      ?.focus();
    // Runs once per settle request; later data changes must not move focus.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settling]);
  const resolved = (review: TeacherReview) => {
    resolvedReviewIds.current.add(review.id);
    setReviews((state) => ({
      ...state,
      reviews: state.reviews?.filter((item) => item.id !== review.id) ?? null,
    }));
    settleRow(review.seat_id);
  };
  // "Mark as reviewed": close this person's review requests here at once (every page reads
  // the same table, so they leave the others too) and let vision reset them to working.
  // Remember the mark until vision moves them out of review, so the row (which may remount in
  // the other group) can't offer it twice, and drop their open requests from the queue now.
  const applyMarked = (marked: string) => {
    setMarkedSeats((previous) => new Set(previous).add(marked));
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
    });
  };
  const markReviewedButton = (sessionId: string | null, seatId: string) =>
    markedSeats.has(seatId) ? (
      <p className="person-note" role="status">
        Marked as reviewed. They’ll show as working again in a moment.
      </p>
    ) : reviewActionsEnabled && client && sessionId ? (
      <MarkReviewedButton
        key={seatId}
        client={client}
        sessionId={sessionId}
        seatId={seatId}
        onMarked={(marked) => {
          applyMarked(marked);
          settleRow(marked);
        }}
      />
    ) : null;
  // Support needed / No support needed for a flagged person with no request:
  // either answer closes the flag (as Mark as reviewed does) and they leave
  // Attention; nothing is written as a review for them.
  const flagDecisions = (sessionId: string | null, seatId: string) =>
    markedSeats.has(seatId) ? (
      <p className="person-note" role="status">
        Saved. They’ll show as working again in a moment.
      </p>
    ) : reviewActionsEnabled && client && sessionId ? (
      <FlagDecisionButtons
        key={seatId}
        client={client}
        sessionId={sessionId}
        seatId={seatId}
        onDecided={(decided) => {
          applyMarked(decided);
          if (selectedId === decided) setSelectedId(null);
          requestAnimationFrame(() =>
            (view === "review" ? pageHeading : listHeading).current?.focus(),
          );
        }}
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
            interventionsEnabled={interventionsEnabled}
            actions={(flaggedIdSet.has(seatId) && pending.length === 0
              ? flagDecisions
              : markReviewedButton)(
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
        reviewPage={reviewPageEnabled}
        reviewCount={waitingCount}
      />
      <main id="main-content" className="dashboard-main">
        {signedOut ? (
          <SignInCard />
        ) : (
          <>
            <section className="ws-hero" aria-labelledby="classroom-heading">
              <header className="page-intro">
                <div>
                  <h1 id="classroom-heading" ref={pageHeading} tabIndex={-1}>
                    {view === "review" ? "to review" : "your classroom"}
                  </h1>
                  {view === "review" || sessionLive ? null : (
                    <p className="ws-subtitle">{activity}</p>
                  )}
                </div>
                {view === "review" ? (
                  <Link className="ws-pill" href="/dashboard">
                    <WorkspaceIcon name="back" />
                    Back to classroom
                  </Link>
                ) : reviewPageEnabled ? (
                  <Link
                    className={`ws-pill review-link${waitingCount ? " has-items" : ""}${companionEnabled ? " has-companion" : ""}`}
                    href="/review"
                  >
                    TO REVIEW
                    {waitingCount ? (
                      // With the companion, keyed so a new count pops in.
                      <span
                        className="ws-count"
                        key={companionEnabled ? waitingCount : undefined}
                      >
                        {waitingCount}
                      </span>
                    ) : null}
                    {companionEnabled ? (
                      <ReviewCompanion
                        count={companionCount}
                        rememberAs={station}
                      />
                    ) : null}
                  </Link>
                ) : null}
              </header>
              {view !== "review" &&
              ((sessionLive && client) || (healthStripEnabled && station)) ? (
                <div className="hero-controls">
                  {sessionLive && client ? (
                    <SessionControls
                      client={client}
                      station={station}
                      onActivity={ignoreActivity}
                      teacherLoginEnabled={teacherLoginEnabled}
                      resetPeople={
                        resetPeopleEnabled
                          ? {
                              seatIds: reviewGroups.map((group) => group.seat_id),
                              // Flagged people without a request have nothing to close, but
                              // their "No suggestion yet" card goes with everyone else's.
                              onReset: (ids) => {
                                [...ids, ...flaggedOnly.map((seat) => seat.id)].forEach(
                                  applyMarked,
                                );
                                // Everyone starts over: nobody is still "just lost".
                                forgetLostPeople();
                              },
                            }
                          : null
                      }
                    />
                  ) : null}
                  {healthStripEnabled && station ? (
                    <CameraHealthStrip
                      station={station}
                      updatedAt={seats.map((seat) => seat.state?.updated_at)}
                      inView={inView.length}
                      conflict={conflict}
                      hostedEnabled={hostedLocalFeedEnabled}
                      hostedOrigin={hostedDashboardOrigin}
                    />
                  ) : null}
                </div>
              ) : null}
              {view !== "review" && sessionLive && conflict && !healthStripEnabled ? (
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
                    onClick={() => retryFeed()}
                  >
                    Try again
                  </button>
                ) : null}
              </section>
            ) : null}

            {view === "review" ? (
              <ReviewPageList
                groups={reviewGroups}
                flagged={flaggedOnly}
                inView={inView}
                nameOf={nameOf}
                activityName={activityName}
                decisions={(lead) =>
                  reviewActionsEnabled && client ? (
                    <TeacherReviewActions
                      key={lead.id}
                      client={client}
                      review={lead}
                      onResolved={resolved}
                      interventionsEnabled={interventionsEnabled}
                    />
                  ) : null
                }
                markReviewed={markReviewedButton}
                flagDecisions={flagDecisions}
                feedProblem={reviewNotice}
                feedLoading={reviews.loading}
                onRetry={retryReviews}
                emptyText={
                  reviewNotice
                    ? null
                    : !reviewsEnabled || configurationError
                      ? "Cues will list people here when someone may need you."
                      : reviewsLive
                        ? "All clear. No one needs you right now."
                        : "Checking…"
                }
              />
            ) : (
              <>
            <div className="monitor-workspace">
              <LocalClassroomFeed hostedEnabled={hostedLocalFeedEnabled} hostedOrigin={hostedDashboardOrigin} />
              <section
                className="ws-panel class-panel"
                aria-labelledby="class-heading"
                onKeyDown={(event) => {
                  if (event.key === "Escape" && selectedId) closeDetails();
                }}
              >
                {selectedPerson ? (
                  <div className="panel-person">
                    <header className="panel-heading">
                      <button
                        type="button"
                        className="ws-icon-button"
                        onClick={() => closeDetails()}
                        aria-label="Back to attention"
                      >
                        <WorkspaceIcon name="back" />
                      </button>
                      <h2 id="class-heading" ref={listHeading} tabIndex={-1}>
                        {selectedPerson.display_name}
                      </h2>
                    </header>
                    <PersonDetails
                      id={`more-${selectedPerson.id}`}
                      presentation={present(selectedPerson)}
                      reviews={[]}
                      stale={false}
                      client={null}
                      onResolved={resolved}
                      actions={markReviewedButton(
                        selectedPerson.state?.session_id ?? null,
                        selectedPerson.id,
                      )}
                    />
                  </div>
                ) : (
                  <>
                <AttentionList
                  headingRef={listHeading}
                  groups={reviewGroups}
                  flagged={flaggedOnly}
                  seats={seats}
                  inView={inView}
                  mixedActivities={mixedActivities}
                  nameOf={nameOf}
                  present={present}
                  renderRow={row}
                  waitingCount={waitingCount}
                  showCount={reviewsLive}
                  feedProblem={reviewNotice}
                  feedLoading={reviews.loading}
                  onRetry={retryReviews}
                  emptyText={
                    reviewNotice
                      ? null
                      : !reviewsEnabled || configurationError
                        ? "Cues will ask here when someone may need you."
                        : reviewsLive
                          ? catchingUp
                            ? "Marked as reviewed. The camera will catch up in a moment."
                            : "All clear. Cues will ask when someone may need you."
                          : "Checking…"
                  }
                />
                  </>
                )}
              </section>
            </div>

            <StudentStrip
              empty={inView.length === 0 ? peopleEmpty : null}
              people={stripEntries(
                inView.map((seat) => {
                  const presentation = present(seat);
                  return {
                    id: seat.id,
                    name: seat.display_name,
                    label: presentation.label,
                    tone: statusTone(presentation),
                    activity: seat.activity,
                  };
                }),
                new Set(reviewGroups.map((group) => group.seat_id)),
                selectedId,
                mixedActivities,
              )}
              onSelect={(id) => setSelectedId(selectedId === id ? null : id)}
              onEscape={selectedId ? (card) => closeDetails(card) : undefined}
            />
              </>
            )}
          </>
        )}

      </main>
    </div>
  );
}
