"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { WorkspaceIcon } from "@/components/workspace-icon";
import CuesMark from "@/components/cues-mark";
import { ThemeToggle } from "@/components/theme-toggle";

// A quiet rail of round buttons: Classroom, Review, Insights, then the teacher's Profile (where
// sign-out, the classroom camera and alerts live). Labels show on hover and
// focus, and screen readers always hear them.
export function WorkspaceSidebar({
  reviewCount = 0,
}: {
  /** People waiting, shown as a dot count on the To review link. */
  reviewCount?: number;
}) {
  // The current entry follows the URL, so each page highlights its own link.
  const pathname = usePathname();
  // First visit only: show every label for a few seconds so the icons are
  // not a guessing game. Browsers without storage simply skip the hint.
  const [hint, setHint] = useState(false);
  useEffect(() => {
    try {
      if (localStorage.getItem("cues-rail-hint")) return;
      localStorage.setItem("cues-rail-hint", "1");
    } catch {
      return;
    }
    const show = window.setTimeout(() => setHint(true), 0);
    const hide = window.setTimeout(() => setHint(false), 6000);
    return () => {
      window.clearTimeout(show);
      window.clearTimeout(hide);
    };
  }, []);
  const current = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`)
      ? { className: "rail-link is-current", "aria-current": "page" as const }
      : { className: "rail-link" };
  return (
    <aside className="workspace-sidebar" data-hint={hint || undefined}>
      <Link href="/" className="rail-brand" aria-label="Cues home">
        <CuesMark className="brand-mark" size={26} />
      </Link>
      <nav className="sidebar-nav" aria-label="Workspace">
        <Link href="/dashboard" {...current("/dashboard")}>
          <WorkspaceIcon name="classroom" />
          <span className="nav-label">Classroom</span>
        </Link>
        <Link href="/review" {...current("/review")}>
            <WorkspaceIcon name="review" />
            <span className="nav-label">
              Review
              {reviewCount ? ` (${reviewCount} waiting)` : ""}
            </span>
            {reviewCount ? (
              <span className="rail-badge" aria-hidden="true">
                {reviewCount}
              </span>
            ) : null}
          </Link>
        <Link href="/insights" {...current("/insights")}>
          <WorkspaceIcon name="insights" />
          <span className="nav-label">Insights</span>
        </Link>
        <Link href="/settings/profile" {...current("/settings")}>
            <WorkspaceIcon name="account" />
            <span className="nav-label">Profile</span>
          </Link>
      </nav>
      <div className="sidebar-bottom">
        <ThemeToggle pageDefault="dark" className="rail-link" />
      </div>
    </aside>
  );
}
