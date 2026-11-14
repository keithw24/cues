import { isEnabled } from "@/lib/flags";

export default async function DashboardPage() {
  if (!isEnabled("web.dashboard")) {
    return (
      <main id="main-content" className="paused-page">
        <div className="wordmark">
          Cues<span className="brand-period">.</span>
        </div>
        <h1>Your classroom, in view.</h1>
        <p>The teacher dashboard is not enabled in this environment.</p>
      </main>
    );
  }
  const { default: Dashboard } = await import("@/components/dashboard");
  return (
    <Dashboard
      personObservationsEnabled={isEnabled("web.person_observations")}
      sessionControlsEnabled={isEnabled("web.session_controls")}
      stationId={process.env.CUES_STATION_ID ?? ""}
      reviewsEnabled={isEnabled("web.teacher_reviews")}
      reviewActionsEnabled={isEnabled("web.teacher_review_actions")}
      teacherLoginEnabled={isEnabled("web.teacher_login")}
    />
  );
}
