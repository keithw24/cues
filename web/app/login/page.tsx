import Link from "next/link";
import { isEnabled } from "@/lib/flags";

export const metadata = { title: "Cues · Teacher sign in" };

export default async function LoginPage() {
  if (!isEnabled("web.teacher_login"))
    return (
      <main id="main-content" className="paused-page">
        <Link className="wordmark" href="/">
          Cues
        </Link>
        <h1>Teacher sign-in is unavailable.</h1>
        <p>This feature is not enabled in this environment.</p>
        <Link href="/dashboard">Open classroom</Link>
      </main>
    );
  const { default: TeacherLogin } = await import("@/components/teacher-login");
  return <TeacherLogin signupEnabled={isEnabled("web.teacher_signup")} />;
}
