import { redirect } from "next/navigation";
import { isEnabled } from "@/lib/flags";
import Dashboard from "@/components/dashboard";
import { dashboardFeatures } from "@/lib/dashboard-features";
import { garamond } from "@/components/workspace-fonts";
import "@/components/workspace.css";

// The To review page (web.review_page): everyone Cues asked about, one card
// each, with the teacher's decision in reach. It is the classroom dashboard in
// its review view, so it reads the same data and stays in sync with it.
export default async function ReviewPage() {
  if (!isEnabled("web.review_page") || !isEnabled("web.dashboard"))
    redirect("/dashboard");
  return (
    <div className={`workspace ${garamond.variable}`}>
      <Dashboard
        view="review"
        features={{ ...dashboardFeatures("review"), reviewPageEnabled: true }}
        stationId={process.env.CUES_STATION_OVERRIDE ?? ""}
      />
    </div>
  );
}
