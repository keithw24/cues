"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { WorkspaceIcon } from "@/components/workspace-icon";
import CuesMark from "@/components/cues-mark";
import { ThemeToggle } from "@/components/theme-toggle";

// A quiet rail of round buttons: Classroom, To review (when on), then the teacher's Profile (where
// sign-out, the classroom camera and alerts live). Labels show on hover and
// focus, and screen readers always hear them.
export function WorkspaceSidebar({
  accountEnabled = false,
  themeToggle = false,
  reviewPage = false,
  reviewCount = 0,
}: {
  accountEnabled?: boolean;
  themeToggle?: boolean;
  /** web.review_page: show the To review link. */
  reviewPage?: boolean;
  /** People waiting, shown as a dot count on the To review link. */
  reviewCount?: number;
}) {
  // The current entry follows the URL, so each page highlights its own link.
  const pathname = usePathname();
  const current = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`)
      ? { className: "rail-link is-current", "aria-current": "page" as const }
      : { className: "rail-link" };
  return (
    <aside className="workspace-sidebar">
      <Link href="/" className="rail-brand" aria-label="Cues home">
        <CuesMark className="brand-mark" size={26} />
      </Link>
      <nav className="sidebar-nav" aria-label="Workspace">
        <Link href="/dashboard" {...current("/dashboard")}>
          <WorkspaceIcon name="classroom" />
          <span className="nav-label">Classroom</span>
        </Link>
        {reviewPage ? (
          <Link href="/review" {...current("/review")}>
            <WorkspaceIcon name="review" />
            <span className="nav-label">
              To review
              {reviewCount ? ` (${reviewCount} waiting)` : ""}
            </span>
            {reviewCount ? (
              <span className="rail-badge" aria-hidden="true">
                {reviewCount}
              </span>
            ) : null}
          </Link>
        ) : null}
        {accountEnabled ? (
          <Link href="/settings/profile" {...current("/settings")}>
            <WorkspaceIcon name="account" />
            <span className="nav-label">Profile</span>
          </Link>
        ) : null}
      </nav>
      <div className="sidebar-bottom">
        {themeToggle ? (
          <ThemeToggle pageDefault="dark" className="rail-link" />
        ) : null}
      </div>
    </aside>
  );
}
