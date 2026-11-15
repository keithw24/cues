import Link from "next/link";
import { isEnabled } from "@/lib/flags";

export default async function ConfirmedPage() {
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
  const { default: SignupConfirmed } = await import(
    "@/components/signup-confirmed"
  );
  return <SignupConfirmed
      profileEnabled={isEnabled("web.teacher_profile")}
      themeToggleEnabled={isEnabled("web.theme_toggle")}
    />;
}
