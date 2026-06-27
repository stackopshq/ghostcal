import { notFound } from "next/navigation";
import BookingClient from "@/components/BookingClient";
import { ApiError, getEventType } from "@/lib/api";

// Embeddable booking widget: /embed/{organization}/{event-type}. Bare frame for an <iframe>.
export default async function EmbedPage({
  params,
}: {
  params: Promise<{ org: string; event: string }>;
}) {
  const { org, event } = await params;

  let eventType;
  try {
    eventType = await getEventType(org, event);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-transparent p-2">
      <BookingClient org={org} event={event} eventType={eventType} />
    </main>
  );
}
