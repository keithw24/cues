import Link from "next/link";
import type { ReactNode } from "react";
import {
  RiArrowRightLine,
  RiHand,
  RiRecordCircleLine,
  RiThumbUpLine,
} from "@remixicon/react";

// A dotted page with inline icon chips, like jmo’s own site.
export default function LandingHero({
  start,
  preview,
}: {
  start: string;
  preview: ReactNode;
}) {
  return (
    <section className="ln-hero" aria-labelledby="hero-heading">
      <div className="ln-hero-dots" aria-hidden="true" />
      <div className="ln-hero-copy">
        <h1 id="hero-heading" className="ln-enter">
          know who needs you next
        </h1>
        <p className="ln-lede ln-enter">
          Cues watches for{" "}
          <span className="ln-inline-chip">
            <RiHand aria-hidden="true" />
            raised hands
          </span>
          ,{" "}
          <span className="ln-inline-chip">
            <RiThumbUpLine aria-hidden="true" />
            thumbs up
          </span>{" "}
          and{" "}
          <span className="ln-inline-chip">
            <RiRecordCircleLine aria-hidden="true" />
            your own gestures
          </span>
          , then suggests support you approve.
        </p>
        <div className="ln-actions ln-enter">
          <Link className="ln-button ln-button-dark" href={start}>
            Get started
            <RiArrowRightLine aria-hidden="true" />
          </Link>
          <a className="ln-text-link" href="#how">
            How it works
          </a>
        </div>
      </div>
      <div className="ln-stage">
        <div className="ln-stage-glow" aria-hidden="true">
          <span className="ln-grain" />
        </div>
        {preview}
      </div>
    </section>
  );
}
