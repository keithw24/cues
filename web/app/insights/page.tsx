import InsightsPage from "@/components/insights/insights-page";
import { garamond } from "@/components/workspace-fonts";
import "@/components/workspace.css";

// The Insights page: what happened across a teacher's finished sessions, and why Cues asked.
// Class-level counts only, read in one request (teacher_insights).
export default function Page() {
  return (
    <div className={`workspace ${garamond.variable}`}>
      <InsightsPage />
    </div>
  );
}
