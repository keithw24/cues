import Link from "next/link";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { isEnabled } from "@/lib/flags";

export const metadata = { title: "Cues · Profile" };

export default async function ProfilePage() {
  const enabled =
    isEnabled("web.teacher_profile") && isEnabled("web.teacher_login");
  const { default: TeacherProfileForm } = enabled
    ? await import("@/components/teacher-profile-form")
    : { default: null };
  return (
    <div className="dashboard-shell">
      <WorkspaceSidebar
        accountEnabled={isEnabled("web.teacher_login")}
        liveView={isEnabled("web.live_view")}
      />
      <main id="main-content" className="dashboard-main settings-main">
        <div className="page-breadcrumb">
          Workspace <span>/</span> Profile
        </div>
        <header className="page-intro">
          <h1>Profile</h1>
          <p>How Cues names you, and where alerts can reach you.</p>
        </header>
        <Link className="quiet-link" href="/settings/stations">Station access</Link>
        {TeacherProfileForm ? (
          <TeacherProfileForm />
        ) : (
          <div className="integration-details">
            <p>Teacher profiles are not enabled in this environment.</p>
            <Link className="quiet-link" href="/dashboard">
              Back to classroom
            </Link>
          </div>
        )}
      </main>
    </div>
  );
}
