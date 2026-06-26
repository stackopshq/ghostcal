import { notFound } from "next/navigation";
import BookingClient from "@/components/BookingClient";
import { ApiError, getEventType } from "@/lib/api";

// Public booking link: /{organization}/{event-type}. Rendered on demand (no-store fetch).
export default async function Page({
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
    <main className="flex flex-1 items-center justify-center p-4 sm:p-8">
      <BookingClient org={org} event={event} eventType={eventType} />
    </main>
  );
}
