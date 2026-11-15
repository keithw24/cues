import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { isEnabled } from "@/lib/flags";
import { garamond } from "@/components/workspace-fonts";
import ProfileAccount from "@/components/profile-account";
import "@/components/workspace.css";
import "@/components/teacher-profile.css";


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
        reviewPage={isEnabled("web.review_page")}
      />
      <main id="main-content" className="dashboard-main settings-main">
        <header className="page-intro">
          <h1>profile</h1>
        </header>
        <div className="settings-list">
          {isEnabled("web.teacher_login") ? <ProfileAccount /> : null}
          {TeacherProfileForm ? (
            <TeacherProfileForm />
          ) : (
            <section className="profile-group">
              <div className="profile-card">
                <h2 className="profile-card-title">name and phone</h2>
                <p className="profile-hint">
                  Not turned on in this environment yet.
                </p>
              </div>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
