import type { ComponentProps } from "react";
import {
  RiArrowDownSLine,
  RiArrowLeftLine,
  RiArrowRightLine,
  RiArrowRightSLine,
  RiArrowRightUpLine,
  RiCheckboxCircleLine,
  RiEyeOffLine,
  RiFlag2Line,
  RiGroupLine,
  RiHand,
  RiInbox2Line,
  RiLayoutGridLine,
  RiLock2Line,
  RiNotification3Line,
  RiPauseCircleLine,
  RiPlayCircleLine,
  RiPulseLine,
  RiRefreshLine,
  RiTimeLine,
  RiUser3Line,
  RiVidiconLine,
} from "@remixicon/react";

// Remix Icon only, so the workspace matches the landing page and sign-up.
const icons = {
  classroom: RiLayoutGridLine,
  live: RiPulseLine,
  people: RiGroupLine,
  review: RiInbox2Line,
  photon: RiNotification3Line,
  arrow: RiArrowRightLine,
  back: RiArrowLeftLine,
  refresh: RiRefreshLine,
  lock: RiLock2Line,
  camera: RiVidiconLine,
  account: RiUser3Line,
  chevronDown: RiArrowDownSLine,
  chevronRight: RiArrowRightSLine,
  hand: RiHand,
  check: RiCheckboxCircleLine,
  arrowUpRight: RiArrowRightUpLine,
  flag: RiFlag2Line,
  paused: RiPauseCircleLine,
  working: RiPlayCircleLine,
  hidden: RiEyeOffLine,
  time: RiTimeLine,
} as const;

export function WorkspaceIcon({
  name,
  ...props
}: ComponentProps<typeof RiLayoutGridLine> & { name: keyof typeof icons }) {
  const Icon = icons[name];
  return <Icon aria-hidden="true" {...props} />;
}
