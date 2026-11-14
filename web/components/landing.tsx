import Link from "next/link";
import type { CSSProperties } from "react";
import { EB_Garamond } from "next/font/google";
import { isEnabled } from "@/lib/flags";
import {
  RiArrowRightLine,
  RiLayoutGridLine,
  RiLightbulbLine,
  RiLock2Line,
  RiVidiconLine,
} from "@remixicon/react";
import LandingHero from "@/components/landing-hero";
import LandingPreview from "@/components/landing-preview";
import LandingDemo from "@/components/landing-demo";
import LandingReveal from "@/components/landing-reveal";
import LandingSteps from "@/components/landing-steps";
import { ThemeToggle } from "@/components/theme-toggle";
import CuesMark from "@/components/cues-mark";
import LandingFaq from "@/components/landing-faq";
import LandingFooter from "@/components/landing-footer";
import "./landing.css";

const garamond = EB_Garamond({
  variable: "--font-garamond",
  subsets: ["latin"],
  weight: ["500"],
  display: "swap",
});

// Every task on this page is a simulated example.
const tasks = [
  { name: "Raise hand", kind: "Built in", count: "2 seats" },
  { name: "Thumbs up", kind: "Built in", count: "3 seats" },
  { name: "Wave hello", kind: "Recorded by you", count: "1 seat" },
  { name: "Touch your nose", kind: "Recorded by you", count: "Not started" },
] as const;

export default function Landing() {
  const start = isEnabled("web.teacher_signup") ? "/signup" : "/login";
  const faq = isEnabled("web.landing_faq");
  const demo = isEnabled("web.landing_demo");
  const themeToggle = isEnabled("web.theme_toggle");
  const motion = isEnabled("web.landing_motion");
  return (
    <div className={`landing ${garamond.variable}`}>
      {motion ? <LandingReveal /> : null}
      <header className="ln-nav">
        <Link href="/" className="ln-brand" aria-label="Cues home">
          <CuesMark className="ln-brand-mark" />
          Cues
        </Link>
        <nav aria-label="Main">
          <a href="#how">How it works</a>
          <a href="#control">Teacher control</a>
          <a href="#privacy">Privacy</a>
          {themeToggle ? (
            <ThemeToggle pageDefault="dark" className="ln-theme-toggle" />
          ) : null}
          <Link
            className="ln-button ln-button-dark ln-button-small"
            href={start}
          >
            Get started
          </Link>
        </nav>
      </header>

      <main id="main-content">
        <LandingHero
          start={start}
          preview={demo ? <LandingDemo /> : <LandingPreview />}
        />

        {demo ? (
          <LandingSteps />
        ) : (
          <>
            <section
              id="how"
              className="ln-section"
              aria-labelledby="how-heading"
            >
              <div
                className="ln-section-copy"
                data-reveal
                style={{ "--i": 0 } as CSSProperties}
              >
                <h2 id="how-heading">Simple tasks, watched for you</h2>
                <p>
                  Pick a task from the list or record your own gesture. One
                  camera follows each student by their place in the frame, and
                  Cues keeps track of who has finished, who is still going and
                  who keeps trying.
                </p>
              </div>
              <div
                className="ln-card"
                data-reveal
                style={{ "--i": 1 } as CSSProperties}
              >
                <p className="ln-card-label">Today’s tasks</p>
                <ul className="ln-rows">
                  {tasks.map((task) => (
                    <li key={task.name}>
                      <span className="ln-row-name">{task.name}</span>
                      <span className="ln-row-kind">{task.kind}</span>
                      <span className="ln-row-count">{task.count}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </section>

            <section
              id="control"
              className="ln-section ln-section-flip"
              aria-labelledby="control-heading"
            >
              <div
                className="ln-section-copy"
                data-reveal
                style={{ "--i": 1 } as CSSProperties}
              >
                <h2 id="control-heading">You decide what changes</h2>
                <p>
                  When a pattern matters, Cues flags who may need you and says
                  why. Nothing about a student’s task, instructions or support
                  changes until you approve it.
                </p>
              </div>
              <div
                className="ln-card"
                data-reveal
                style={{ "--i": 0 } as CSSProperties}
              >
                <p className="ln-card-label">Waiting for you</p>
                <div className="ln-approval">
                  <p className="ln-seat-meta">Seat 2 · Raise hand</p>
                  <p className="ln-approval-title">
                    Break the task into two steps
                  </p>
                  <p className="ln-approval-why">
                    <RiLightbulbLine />
                    Why: three attempts in two minutes, no completion yet.
                  </p>
                  <div className="ln-suggestion-actions">
                    <span className="ln-button ln-button-dark ln-button-small">
                      Approve
                    </span>
                    <span className="ln-button ln-button-outline ln-button-small">
                      Not now
                    </span>
                  </div>
                </div>
              </div>
            </section>
          </>
        )}

        <section
          id="privacy"
          className="ln-privacy"
          aria-labelledby="privacy-heading"
        >
          <h2
            id="privacy-heading"
            data-reveal
            style={{ "--i": 0 } as CSSProperties}
          >
            The camera stays in the classroom
          </h2>
          <p data-reveal style={{ "--i": 1 } as CSSProperties}>
            Video stays on the station laptop. Only structured status updates,
            such as “Seat 1 finished thumbs up”, leave it.
          </p>
          <ul className="ln-facts">
            <li data-reveal style={{ "--i": 2 } as CSSProperties}>
              <RiVidiconLine />
              <strong>Video stays local</strong>
              <span>Frames and images never leave the laptop.</span>
            </li>
            <li data-reveal style={{ "--i": 3 } as CSSProperties}>
              <RiLayoutGridLine />
              <strong>No face recognition</strong>
              <span>A seat is known only by its place in the frame.</span>
            </li>
            <li data-reveal style={{ "--i": 4 } as CSSProperties}>
              <RiLock2Line />
              <strong>You stay in control</strong>
              <span>
                Every change to a task, instruction or support waits for your
                approval.
              </span>
            </li>
          </ul>
        </section>

        {faq ? <LandingFaq /> : null}

        <section className="ln-cta" aria-labelledby="cta-heading" data-reveal>
          <h2 id="cta-heading">a little support. more room to teach.</h2>
          <div className="ln-actions">
            <Link className="ln-button ln-button-light" href={start}>
              Get started
              <RiArrowRightLine aria-hidden="true" />
            </Link>
            <Link className="ln-button ln-button-ghost" href="/dashboard">
              Open the classroom
            </Link>
          </div>
        </section>
      </main>

      {faq ? (
        <LandingFooter start={start} />
      ) : (
        <footer className="ln-footer">
          <span>Cues</span>
          <span>Built for special-education classrooms.</span>
        </footer>
      )}
    </div>
  );
}
