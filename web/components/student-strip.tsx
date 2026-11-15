"use client";

import { useEffect, useRef, useState } from "react";
import { initials } from "@/components/workspace-rows";
import type { StripEntry } from "@/lib/classroom-view";
import { WorkspaceIcon } from "@/components/workspace-icon";

export type StripPerson = StripEntry;

// Everyone the camera sees, left to right as in the frame, as cards you can
// slide through under the camera. Arrows sit on the row's ends and appear only
// on a side that has more cards. Status is a word on every card; the ring color supports it.
export function StudentStrip({
  people,
  empty,
  onSelect,
  onEscape,
}: {
  people: StripPerson[];
  /** The message to show when no one is in view, or null. */
  empty: string | null;
  onSelect: (id: string) => void;
  /** Closes a person opened from the row (Escape on a card). */
  onEscape?: () => void;
}) {
  const track = useRef<HTMLUListElement>(null);
  const [edges, setEdges] = useState({ start: true, end: true });
  useEffect(() => {
    const node = track.current;
    if (!node) return;
    const measure = () =>
      setEdges({
        start: node.scrollLeft <= 2,
        end: node.scrollLeft + node.clientWidth >= node.scrollWidth - 2,
      });
    measure();
    node.addEventListener("scroll", measure, { passive: true });
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => {
      node.removeEventListener("scroll", measure);
      observer.disconnect();
    };
  }, [people.length]);
  const slide = (direction: 1 | -1) => {
    const node = track.current;
    if (!node) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    node.scrollBy({
      left: direction * node.clientWidth * 0.8,
      behavior: reduce ? "auto" : "smooth",
    });
  };
  return (
    <section className="student-strip" aria-label="Everyone in view">
      {empty ? (
        <p className="panel-empty strip-empty" role="status">
          {empty}
        </p>
      ) : (
        <ul
          className="strip-track"
          ref={track}
          data-more-before={!edges.start || undefined}
          data-more-after={!edges.end || undefined}
        >
          {people.map((person) => (
            <li key={person.id}>
              <button
                type="button"
                className={`strip-card is-${person.tone}`}
                aria-pressed={person.selected}
                aria-controls={`more-${person.id}`}
                onClick={() => onSelect(person.id)}
                onKeyDown={(event) => {
                  if (event.key === "Escape" && onEscape) onEscape();
                }}
              >
                <span className="row-avatar is-ring" aria-hidden="true">
                  {initials(person.name)}
                </span>
                <span className="row-body">
                  <span className="row-name">{person.name}</span>
                  <span className="strip-status">{person.status}</span>
                  {person.activity ? (
                    <span className="row-caption">{person.activity}</span>
                  ) : null}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {empty || (edges.start && edges.end) ? null : (
        <>
          <button
            type="button"
            className="ws-icon-button strip-arrow is-before"
            aria-label="Show earlier people"
            hidden={edges.start}
            onClick={() => slide(-1)}
          >
            <WorkspaceIcon name="back" />
          </button>
          <button
            type="button"
            className="ws-icon-button strip-arrow is-after"
            aria-label="Show more people"
            hidden={edges.end}
            onClick={() => slide(1)}
          >
            <WorkspaceIcon name="arrow" />
          </button>
        </>
      )}
    </section>
  );
}
