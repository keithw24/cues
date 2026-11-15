import Link from "next/link";
import type { ReactNode } from "react";
import {
  RiArrowRightLine,
  RiHand,
  RiRepeatLine,
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
          {/* Each chip keeps its comma: a line never starts with one. */}
          <span className="ln-chip-group">
            <span className="ln-inline-chip">
              <RiHand aria-hidden="true" />
              raised hands
            </span>
            ,
          </span>{" "}
          <span className="ln-inline-chip">
            <RiThumbUpLine aria-hidden="true" />
            thumbs up
          </span>{" "}
          and{" "}
          <span className="ln-chip-group">
            <span className="ln-inline-chip">
              <RiRepeatLine aria-hidden="true" />
              who keeps trying
            </span>
            ,
          </span>{" "}
          then suggests support you approve.
        </p>
        <div className="ln-actions ln-enter">
          <Link className="ln-button ln-button-dark" href={start}>
            Get Started
            <RiArrowRightLine aria-hidden="true" />
          </Link>
          <a className="ln-text-link" href="#how">
            How It Works
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
