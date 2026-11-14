import { WorkspaceIcon } from "@/components/workspace-icon";
import type { NextUp } from "@/lib/next-up";

// One answer to "who needs me?". It opens the review in the details drawer,
// where the existing actions live; nothing is resolved from here.
export function NextUpCard({
  next,
  summary,
  onOpen,
}: {
  next: NextUp;
  /** A one-line count, e.g. "4 in view · 3 working · 1 finished". */
  summary?: string;
  onOpen: () => void;
}) {
  return (
    <section className="next-up" aria-labelledby="next-up-heading">
      <h2 id="next-up-heading">Who needs you next</h2>
      {next.kind === "calm" ? (
        <>
          <p className="next-up-calm">{next.message}</p>
          {summary ? <p className="next-up-summary">{summary}</p> : null}
        </>
      ) : (
        <>
          <p className="next-up-name">
            {next.kind === "review" && next.elevated ? (
              <span className="next-up-flag">
                <WorkspaceIcon name="flag" />
                <span className="sr-only">Elevated priority</span>
              </span>
            ) : null}
            {next.name}
          </p>
          <p className="next-up-detail">{next.detail}</p>
          <button type="button" className="next-up-open" onClick={onOpen}>
            {next.kind === "review" ? "Open review" : "Open details"}
            <WorkspaceIcon name="arrow" />
          </button>
          {next.then.length ? (
            <p className="next-up-then">Then: {next.then.join(", ")}</p>
          ) : null}
        </>
      )}
    </section>
  );
}
