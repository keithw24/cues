import Link from "next/link";
import { EB_Garamond } from "next/font/google";
import {
  RiArrowRightLine,
} from "@remixicon/react";
import LandingHero from "@/components/landing-hero";
import LandingDemo from "@/components/landing-demo";
import LandingNeeds from "@/components/landing-needs";
import LandingThemeDefault from "@/components/landing-theme-default";
import LandingReveal from "@/components/landing-reveal";
import LandingAmbient from "@/components/landing-ambient";
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

export default function Landing() {
  const start = "/signup";
  return (
    <div
      className={`landing ${garamond.variable}`}
      data-motion="true"
    >
      <LandingThemeDefault />
      <>
          <LandingReveal />
          <LandingAmbient />
        </>
      <header className="ln-nav">
        <Link href="/" className="ln-brand" aria-label="Cues home">
          <CuesMark className="ln-brand-mark" />
        </Link>
        <nav aria-label="Main">
          <ThemeToggle pageDefault="light" className="ln-theme-toggle" />
          <Link
            className="ln-button ln-button-dark ln-button-small"
            href={start}
          >
            Get Started
          </Link>
        </nav>
      </header>

      <main id="main-content">
        <LandingHero
          start={start}
          preview={<LandingDemo companion />}
        />

        <LandingSteps />

        <LandingNeeds />

        <LandingFaq />

        <section className="ln-cta" aria-labelledby="cta-heading" data-reveal>
          <h2 id="cta-heading">quiet help for a busy classroom.</h2>
          <p className="ln-cta-sub">
            Cues shows who needs you. You decide what happens next. Student camera
            images stay on your laptop.
          </p>
          <div className="ln-actions">
            <Link className="ln-button ln-button-light" href={start}>
              Get Started
              <RiArrowRightLine aria-hidden="true" />
            </Link>
            <Link className="ln-button ln-button-ghost" href="/dashboard">
              Open the Classroom
            </Link>
          </div>
        </section>
      </main>

      <LandingFooter start={start} needs />
    </div>
  );
}
