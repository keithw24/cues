import Landing from "@/components/landing";
import { isEnabled } from "@/lib/flags";
import DashboardPage from "./dashboard/page";
export const instant = false;

export default async function Home() {
  if (!isEnabled("web.landing")) return DashboardPage();
  return <Landing />;
}
