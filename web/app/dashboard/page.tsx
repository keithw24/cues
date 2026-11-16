import { isEnabled } from "@/lib/flags";
import Dashboard from "@/components/dashboard";
import { dashboardFeatures } from "@/lib/dashboard-features";
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
  return (
    <div className={`workspace ${garamond.variable}`}>
      <Dashboard
        features={dashboardFeatures("classroom")}
        hostedDashboardOrigin={process.env.NEXT_PUBLIC_CUES_HOSTED_ORIGIN ?? "https://cues.nyc"}
        stationId={process.env.CUES_STATION_OVERRIDE ?? ""}
      />
    </div>
  );
}
