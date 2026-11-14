import Link from "next/link";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { isEnabled } from "@/lib/flags";
import { garamond } from "@/components/workspace-fonts";
import "@/components/workspace.css";

export const metadata = { title: "Cues · Station access" };

export default async function StationsPage() {
  const enabled = isEnabled("web.teacher_login");
  const Form = enabled ? (await import("@/components/station-pairing-form")).default : null;
  return <div className={`workspace dashboard-shell ${garamond.variable}`}>
    <WorkspaceSidebar accountEnabled={enabled} />
    <main id="main-content" className="dashboard-main settings-main">
      <header className="page-intro"><h1>Station access</h1><p>Connect this account to a classroom station.</p></header>
      {Form ? <Form /> : <div className="integration-details"><p>Teacher accounts are not enabled in this environment.</p><Link href="/dashboard">Back to classroom</Link></div>}
    </main>
  </div>;
}
