import { redirect } from "next/navigation";

// The dashboard home is the event-types view (like Calendly's "Scheduling").
export default function DashboardPage() {
  redirect("/dashboard/event-types");
}
