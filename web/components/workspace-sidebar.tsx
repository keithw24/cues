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
        <span className="brand-symbol" aria-hidden="true">
          <i />
          <i />
        </span>
        Cues
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
      <div className="workspace-name">
        <span className="workspace-monogram">C</span>
        <span>
          Classroom workspace<small>Teacher view</small>
        </span>
      </div>
      <nav className="sidebar-nav" aria-label="Workspace">
        <Link
          href="/dashboard"
          className={!notifications ? "is-current" : ""}
          aria-current={!notifications ? "page" : undefined}
        >
          <WorkspaceIcon name="classroom" />
          Classroom
        </Link>
        <Link href="/dashboard#seats-heading">
          <WorkspaceIcon name="people" />
          People
        </Link>
        <Link href="/dashboard#attention-panel" onClick={onReviews}>
          <WorkspaceIcon name="review" />
          Teacher reviews
        </Link>
      </nav>
      <div className="sidebar-bottom">
        <Link
          className={`sidebar-settings ${notifications ? "is-current" : ""}`}
          href="/settings/notifications"
          aria-current={notifications ? "page" : undefined}
        >
          <WorkspaceIcon name="photon" />
          Notifications<span className="soon-label">Soon</span>
        </Link>
        <div className="sidebar-privacy">
          <WorkspaceIcon name="lock" />
          <span>
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
            <span>
              Teacher account<small>Sign in or manage access</small>
            </span>
            <WorkspaceIcon name="arrow" />
          </Link>
        ) : (
          <div className="sidebar-account">
            <span className="account-monogram">
              <WorkspaceIcon name="account" />
            </span>
            <span>
              Teacher workspace<small>Account access unavailable</small>
            </span>
          </div>
        )}
      </div>
    </aside>
  );
}
