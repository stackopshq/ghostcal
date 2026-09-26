import { redirect } from "next/navigation";

// The dashboard home is the month view.
//
// It used to be the event-types list, on the model of Calendly's "Scheduling" tab. That is the
// right landing page for someone configuring what can be booked, and the wrong one for someone
// opening the app — which is most openings. A calendar application that opens on a settings list
// asks the reader to navigate before it tells them anything, and what they came for is almost
// always the same question: what does my week look like.
export default function DashboardPage() {
  redirect("/dashboard/calendar");
}
