import { redirect } from "next/navigation";

// Text alerts are set up on the Profile page, next to the alert phone.
export default function NotificationsPage() {
  redirect("/settings/profile#notifications");
}
