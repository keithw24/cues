import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { garamond } from "@/components/workspace-fonts";
import ProfileAccount from "@/components/profile-account";
import TeacherProfileForm from "@/components/teacher-profile-form";
import "@/components/workspace.css";
import "@/components/teacher-profile.css";

export default async function ProfilePage() {
  return (
    <div className={`workspace dashboard-shell ${garamond.variable}`}>
      <WorkspaceSidebar />
      <main id="main-content" className="dashboard-main settings-main">
        <header className="page-intro">
          <h1>profile</h1>
        </header>
        <div className="settings-list">
          <ProfileAccount />
          <TeacherProfileForm />
        </div>
      </main>
    </div>
  );
}
