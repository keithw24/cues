import Link from "next/link";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { isEnabled } from "@/lib/flags";
import { garamond } from "@/components/workspace-fonts";
import "@/components/workspace.css";

export const metadata = { title: "Cues · Live" };

// The Live screen (web.live_view): who the station camera sees right now,
// their task status and the review queue, read from Supabase.
export default async function LivePage() {
  if (!isEnabled("web.live_view"))
    return (
      <main id="main-content" className="paused-page">
        <Link className="wordmark" href="/">
          Cues
        </Link>
        <h1>The live view is not enabled.</h1>
        <p>This feature is not enabled in this environment.</p>
        <Link href="/dashboard">Open classroom</Link>
      </main>
    );
  const { default: LiveConnected } =
    await import("@/components/live-connected");
  const screen = (
    <LiveConnected
      visionStationConfigEnabled={isEnabled("web.vision_station_config")}
      liveProgressEnabled={isEnabled("web.live_progress")}
        personObservationsEnabled={isEnabled("web.person_observations")}
      reviewsEnabled={isEnabled("web.teacher_reviews")}
      reviewActionsEnabled={isEnabled("web.teacher_review_actions")}
      teacherLoginEnabled={isEnabled("web.teacher_login")}
    />
  );
  return (
    <div className={`dashboard-shell ${garamond.variable}`}>
      <WorkspaceSidebar
        accountEnabled={isEnabled("web.teacher_login")}
        themeToggle={isEnabled("web.theme_toggle")}
        liveView
      />
      <main id="main-content">{screen}</main>
    </div>
  );
}
