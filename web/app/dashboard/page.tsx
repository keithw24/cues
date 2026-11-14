import { isEnabled } from "@/lib/flags";
import { garamond } from "@/components/workspace-fonts";
import "@/components/workspace.css";

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
    <div className={`workspace ${garamond.variable}`}>
      <Dashboard
        personObservationsEnabled={isEnabled("web.person_observations")}
        sessionControlsEnabled={isEnabled("web.session_controls")}
        stationId={process.env.CUES_STATION_OVERRIDE ?? ""}
        reviewsEnabled={isEnabled("web.teacher_reviews")}
        reviewActionsEnabled={isEnabled("web.teacher_review_actions")}
        teacherLoginEnabled={isEnabled("web.teacher_login")}
        simulatedNamesEnabled={isEnabled("web.simulated_names")}
        roomViewEnabled={isEnabled("web.room_view")}
        themeToggleEnabled={isEnabled("web.theme_toggle")}
        liveViewEnabled={isEnabled("web.live_view")}
        visionStationConfigEnabled={isEnabled("web.vision_station_config")}
      />
    </div>
  );
}
