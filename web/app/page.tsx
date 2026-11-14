import type { Metadata } from "next";
import Landing from "@/components/landing";
import { isEnabled } from "@/lib/flags";
import DashboardPage from "./dashboard/page";
export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  return isEnabled("web.landing")
    ? { title: "Cues · Know who needs you next" }
    : {};
}

export default async function Home() {
  if (!isEnabled("web.landing")) return DashboardPage();
  return <Landing />;
}
