import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError, getBookingPage } from "@/lib/api";

const LOCATION_LABELS: Record<string, string> = {
  google_meet: "Google Meet",
  ms_teams: "Microsoft Teams",
  zoom: "Zoom",
  in_person: "In person",
  phone: "Phone",
  custom: "Custom",
};

// Public host landing page: lists an organization's bookable event types.
export default async function HostPage({ params }: { params: Promise<{ org: string }> }) {
  const { org } = await params;

  let page;
  try {
    page = await getBookingPage(org);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 p-6 sm:p-12">
      <div className="flex items-center gap-3">
        <span className="text-2xl text-accent">●</span>
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">
          {page.organization_name}
        </h1>
      </div>
      <p className="-mt-4 text-muted">Pick a meeting type to book a time.</p>

      {page.event_types.length === 0 ? (
        <p className="text-sm text-muted">No bookable meeting types yet.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {page.event_types.map((et) => (
            <Link
              key={et.id}
              href={`/${org}/${et.id}`}
              className="glass flex flex-col gap-2 rounded-2xl border-l-[3px] border-l-accent p-5 transition hover:border-accent hover:shadow-[0_0_24px_rgba(0,240,255,0.18)]"
            >
              <p className="font-medium text-foreground">{et.title}</p>
              <p className="text-sm text-muted">
                {et.duration_min} min · {LOCATION_LABELS[et.location_type] ?? et.location_type}
              </p>
              {et.description && (
                <p className="line-clamp-2 text-sm text-muted/80">{et.description}</p>
              )}
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
