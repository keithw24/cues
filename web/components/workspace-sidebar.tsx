"use client";

import Link from "next/link";
import { WorkspaceIcon } from "@/components/workspace-icon";

export function WorkspaceSidebar({
  accountEnabled = false,
  notifications = false,
  onReviews,
}: {
  accountEnabled?: boolean;
  notifications?: boolean;
  onReviews?: () => void;
}) {
  return (
    <aside className="workspace-sidebar">
      <Link href="/" className="wordmark" aria-label="Cues home">
        {/* Placeholder mark until the logo is designed. */}
        <span className="brand-mark" aria-hidden="true">
          <i />
          <i />
        </span>
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
          <Link href="/settings/profile">Teacher profile</Link>
        ) : null}
        <Link
          href="/dashboard"
          className={!notifications ? "is-current" : ""}
          aria-current={!notifications ? "page" : undefined}
        >
          <WorkspaceIcon name="classroom" />
          <span className="nav-label">Classroom</span>
        </Link>
        <Link href="/dashboard#seats-heading">
          <WorkspaceIcon name="people" />
          <span className="nav-label">People</span>
        </Link>
        <Link href="/dashboard#attention-panel" onClick={onReviews}>
          <WorkspaceIcon name="review" />
          <span className="nav-label">Teacher reviews</span>
        </Link>
        <Link
          className={notifications ? "is-current" : ""}
          href="/settings/notifications"
          aria-current={notifications ? "page" : undefined}
        >
          <WorkspaceIcon name="photon" />
          <span className="nav-label">Notifications</span>
          <span className="soon-label">Soon</span>
        </Link>
      </nav>
      <div className="sidebar-bottom">
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
