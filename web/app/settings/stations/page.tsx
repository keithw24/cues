import { redirect } from "next/navigation";

// Cameras are no longer paired with a code: the signed-in teacher's classroom
// is created on first sign-in, and the dashboard tells this laptop's camera
// service which classroom it belongs to.
export default function StationsPage() {
  redirect("/dashboard");
}
