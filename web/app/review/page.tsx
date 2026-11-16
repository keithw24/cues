import Dashboard from "@/components/dashboard";
import { garamond } from "@/components/workspace-fonts";
import "@/components/workspace.css";

// The To review page: everyone Cues asked about, one card each, with the teacher's decision
// in reach. It is the classroom dashboard in its review view, so it reads the same data and
// stays in sync with it.
export default async function ReviewPage() {
  return (
    <div className={`workspace ${garamond.variable}`}>
      <Dashboard view="review" stationId={process.env.CUES_STATION_OVERRIDE ?? ""} />
    </div>
  );
}
