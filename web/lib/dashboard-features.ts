import { isEnabled } from "./flags.ts";

/** Every feature flag the dashboard reads, resolved once on the server. */
export type DashboardFeatures = {
  reviewPageEnabled: boolean;
  liveProgressEnabled: boolean;
  personObservationsEnabled: boolean;
  sessionControlsEnabled: boolean;
  reviewsEnabled: boolean;
  reviewActionsEnabled: boolean;
  teacherLoginEnabled: boolean;
  themeToggleEnabled: boolean;
  hostedLocalFeedEnabled: boolean;
  companionEnabled: boolean;
  visionStationConfigEnabled: boolean;
  healthStripEnabled: boolean;
  interventionsEnabled: boolean;
  resetPeopleEnabled: boolean;
  reviewWaitingEnabled: boolean;
};

/**
 * The flags for the classroom page, or for the To review page ("review"), which has never
 * shown the camera health strip, the companion, reset-people or the hosted local feed.
 */
export function dashboardFeatures(view: "classroom" | "review"): DashboardFeatures {
  const classroom = view === "classroom";
  return {
    reviewPageEnabled: isEnabled("web.review_page"),
    liveProgressEnabled: isEnabled("web.live_progress"),
    personObservationsEnabled: isEnabled("web.person_observations"),
    sessionControlsEnabled: isEnabled("web.session_controls"),
    reviewsEnabled: isEnabled("web.teacher_reviews"),
    reviewActionsEnabled: isEnabled("web.teacher_review_actions"),
    teacherLoginEnabled: isEnabled("web.teacher_login"),
    themeToggleEnabled: isEnabled("web.theme_toggle"),
    hostedLocalFeedEnabled: classroom && isEnabled("web.hosted_local_feed"),
    companionEnabled: classroom && isEnabled("web.companion"),
    visionStationConfigEnabled: isEnabled("web.vision_station_config"),
    healthStripEnabled: classroom && isEnabled("web.health_strip"),
    interventionsEnabled: isEnabled("web.interventions"),
    resetPeopleEnabled: classroom && isEnabled("web.reset_people"),
    reviewWaitingEnabled: isEnabled("web.review_waiting"),
  };
}
