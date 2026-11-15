import { redirect } from "next/navigation";

// The Live screen was folded into Classroom: one place for people, counts and
// the requests that need the teacher.
export default function LivePage() {
  redirect("/dashboard");
}
