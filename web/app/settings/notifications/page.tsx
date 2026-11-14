import Link from "next/link";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { WorkspaceIcon } from "@/components/workspace-icon";
import { isEnabled } from "@/lib/flags";

export const metadata = { title: "Cues · Notifications" };

export default function NotificationsPage() {
  return (
    <div className="dashboard-shell">
      <WorkspaceSidebar
        accountEnabled={isEnabled("web.teacher_login")}
        notifications
      />
      <main id="main-content" className="dashboard-main settings-main">
        <div className="page-breadcrumb">
          Workspace <span>/</span> Notifications
        </div>
        <header className="page-intro">
          <h1>Notifications</h1>
          <p>Stay close to your classroom, wherever you are.</p>
        </header>
        <section
          className="integration-section"
          aria-labelledby="photon-heading"
        >
          <div className="integration-icon">
            <WorkspaceIcon name="photon" />
          </div>
          <div>
            <div className="integration-heading">
              <h2 id="photon-heading">Photon</h2>
              <span className="status-chip">Coming soon</span>
            </div>
            <p>
              Get a short message when a classroom review needs your attention.
            </p>
          </div>
        </section>
        <div className="integration-details">
          <h3>A quieter way to stay informed.</h3>
          <p>
            Photon notifications will point you back to a review in Cues. Task
            and support changes will still need your approval.
          </p>
          <dl>
            <div>
              <dt>Connection</dt>
              <dd>Not connected</dd>
            </div>
            <div>
              <dt>Delivery</dt>
              <dd>Not yet available</dd>
            </div>
            <div>
              <dt>Message content</dt>
              <dd>
                Minimal classroom context. No images or expression labels.
              </dd>
            </div>
          </dl>
          <p className="integration-note">
            Photon routing is planned. There’s nothing to configure yet.
          </p>
          <Link className="quiet-link" href="/dashboard">
            Back to classroom <WorkspaceIcon name="arrow" />
          </Link>
        </div>
      </main>
    </div>
  );
}
