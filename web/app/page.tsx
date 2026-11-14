import { isEnabled } from "@/lib/flags";

export default async function Home() {
  if (!isEnabled("web.dashboard")) {
    return (
      <main id="main-content" className="paused-page">
        <div className="wordmark">
          Cues<span className="wordmark-period">.</span>
        </div>
        <h1>Your classroom, in view.</h1>
        <p>The teacher dashboard is not enabled in this environment.</p>
      </main>
    );
  }
  const { default: Dashboard } = await import("@/components/dashboard");
  return <Dashboard />;
}
