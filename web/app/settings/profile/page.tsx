import Link from "next/link";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { WorkspaceIcon } from "@/components/workspace-icon";
import { isEnabled } from "@/lib/flags";
import { garamond } from "@/components/workspace-fonts";
import ProfileAccount from "@/components/profile-account";
import "@/components/workspace.css";

export const metadata = { title: "Cues · Profile" };

export default async function ProfilePage() {
  const enabled =
    isEnabled("web.teacher_profile") && isEnabled("web.teacher_login");
  const { default: TeacherProfileForm } = enabled
    ? await import("@/components/teacher-profile-form")
    : { default: null };
  return (
    <div className={`workspace dashboard-shell ${garamond.variable}`}>
      <WorkspaceSidebar
        accountEnabled={isEnabled("web.teacher_login")}
        themeToggle={isEnabled("web.theme_toggle")}
        liveView={isEnabled("web.live_view")}
      />
      <main id="main-content" className="dashboard-main settings-main">
        <header className="page-intro">
          <h1>Profile</h1>
          <p>How Cues names you, and where alerts can reach you.</p>
        </header>
        <div className="settings-list">
          {isEnabled("web.teacher_login") ? <ProfileAccount /> : null}
          <Link className="settings-row" href="/settings/stations">
            <span className="settings-row-body">
              <strong>Classroom camera</strong>
              <span>Link this account to the camera in your classroom.</span>
            </span>
            <WorkspaceIcon name="arrow" />
          </Link>
          {TeacherProfileForm ? (
            <TeacherProfileForm />
          ) : (
            <section className="settings-row is-static">
              <span className="settings-row-body">
                <strong>Name and alert phone</strong>
                <span>Not turned on in this environment yet.</span>
              </span>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
