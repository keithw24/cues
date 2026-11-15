import Link from "next/link";
import { isEnabled } from "@/lib/flags";
import TeacherLogin from "@/components/teacher-login";

export default async function SignupPage() {
  if (!isEnabled("web.teacher_signup"))
    return (
      <main id="main-content" className="paused-page">
        <Link className="wordmark" href="/">
          Cues
        </Link>
        <h1>Teacher sign-up is unavailable.</h1>
        <p>This feature is not enabled in this environment.</p>
        <Link href="/login">Teacher sign in</Link>
      </main>
    );
  return (
    <TeacherLogin
      mode="signup"
      phoneEnabled={isEnabled("web.alert_phone")}
      profileEnabled={isEnabled("web.teacher_profile")}
      themeToggleEnabled={isEnabled("web.theme_toggle")}
    />
  );
}
