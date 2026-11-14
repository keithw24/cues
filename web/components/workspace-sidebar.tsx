"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { WorkspaceIcon } from "@/components/workspace-icon";
import CuesMark from "@/components/cues-mark";
import { ThemeToggle } from "@/components/theme-toggle";

export function WorkspaceSidebar({
  accountEnabled = false,
  themeToggle = false,
  liveView = false,
  onReviews,
}: {
  accountEnabled?: boolean;
  themeToggle?: boolean;
  /** Show the Live screen (web.live_view) in the rail. */
  liveView?: boolean;
  onReviews?: () => void;
}) {
  // The current entry follows the URL, so /live, /dashboard and settings
  // each highlight their own link.
  const pathname = usePathname();
  const current = (href: string) =>
    pathname === href
      ? { className: "is-current", "aria-current": "page" as const }
      : {};
  return (
    <aside className="workspace-sidebar">
      <Link href="/" className="wordmark" aria-label="Cues home">
        <CuesMark className="brand-mark" />
        <span className="nav-label">Cues</span>
      </Link>
      {accountEnabled ? (
        <Link
          href="/login"
          className="mobile-account"
          aria-label="Teacher account"
        >
          <WorkspaceIcon name="account" />
        </Link>
      ) : null}
      <nav className="sidebar-nav" aria-label="Workspace">
        {accountEnabled ? (
          <Link href="/settings/profile" {...current("/settings/profile")}>
            <WorkspaceIcon name="account" />
            <span className="nav-label">Teacher profile</span>
          </Link>
        ) : null}
        <Link href="/dashboard" {...current("/dashboard")}>
          <WorkspaceIcon name="classroom" />
          <span className="nav-label">Classroom</span>
        </Link>
        {liveView ? (
          <Link href="/live" {...current("/live")}>
            <WorkspaceIcon name="live" />
            <span className="nav-label">Live</span>
          </Link>
        ) : null}
        <Link href="/dashboard#seats-heading">
          <WorkspaceIcon name="people" />
          <span className="nav-label">People</span>
        </Link>
        <Link href="/dashboard#attention-panel" onClick={onReviews}>
          <WorkspaceIcon name="review" />
          <span className="nav-label">Teacher reviews</span>
        </Link>
        <Link
          href="/settings/notifications"
          {...current("/settings/notifications")}
        >
          <WorkspaceIcon name="photon" />
          <span className="nav-label">Notifications</span>
          <span className="soon-label">Soon</span>
        </Link>
      </nav>
      <div className="sidebar-bottom">
        {themeToggle ? (
          <ThemeToggle pageDefault="dark" className="rail-theme-toggle" />
        ) : null}
        <div className="sidebar-privacy">
          <WorkspaceIcon name="lock" />
          <span className="nav-label">
            Camera stays local.
            <br />
            Decisions stay with you.
          </span>
        </div>
        {accountEnabled ? (
          <Link className="sidebar-account" href="/login">
            <span className="account-monogram">
              <WorkspaceIcon name="account" />
            </span>
            <span className="nav-label">
              Teacher account<small>Sign in or manage access</small>
            </span>
          </Link>
        ) : (
          <div className="sidebar-account">
            <span className="account-monogram">
              <WorkspaceIcon name="account" />
            </span>
            <span className="nav-label">
              Teacher workspace<small>Account access unavailable</small>
            </span>
          </div>
        )}
      </div>
    </aside>
  );
}
