import Dashboard from "@/components/dashboard";
import { garamond } from "@/components/workspace-fonts";
import "@/components/workspace.css";

export default async function DashboardPage() {
  return (
    <div className={`workspace ${garamond.variable}`}>
      <Dashboard stationId={process.env.CUES_STATION_OVERRIDE ?? ""} />
    </div>
  );
}
