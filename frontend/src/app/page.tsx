// Public booking page — visual prototype of the GhostCal design system.
// Static demo data for now; wired to the availability API in a later step.

const HOST = {
  org: "Stackops",
  name: "Kevin Allioli",
  initials: "KA",
  event: "Tech Review",
  duration: "60 min",
  location: "Google Meet",
  description:
    "A focused architecture and code walkthrough. Bring your repo — we ghost through it together.",
};

const DAYS = [
  { d: 23, available: false },
  { d: 24, available: true },
  { d: 25, available: true },
  { d: 26, available: true, selected: true },
  { d: 27, available: false },
  { d: 28, available: true },
  { d: 29, available: false },
];

const SLOTS = ["09:00", "09:30", "10:00", "11:30", "14:00", "14:30", "16:00"];

function Icon({ path }: { path: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-4 w-4 shrink-0 text-accent"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={path} />
    </svg>
  );
}

const ICONS = {
  clock: "M12 7v5l3 2M12 21a9 9 0 100-18 9 9 0 000 18z",
  video: "M15 10l5-3v10l-5-3v-4zM3 7a2 2 0 012-2h8a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7z",
  calendar:
    "M8 3v3M16 3v3M4 8h16M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1z",
};

export default function BookingPage() {
  return (
    <main className="flex flex-1 items-center justify-center p-4 sm:p-8">
      <div className="glass grid w-full max-w-5xl overflow-hidden rounded-2xl shadow-2xl md:grid-cols-[minmax(0,22rem)_1fr]">
        {/* Host panel */}
        <aside className="flex flex-col gap-6 border-b border-border p-8 md:border-b-0 md:border-r">
          <div className="flex items-center gap-2 text-sm font-medium tracking-wide text-muted">
            <span className="text-accent">●</span> {HOST.org}
          </div>

          <div className="flex items-center gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-accent/30 to-accent/5 text-lg font-semibold text-accent ring-1 ring-border-strong">
              {HOST.initials}
            </div>
            <div>
              <p className="text-sm text-muted">{HOST.name}</p>
              <h1 className="text-xl font-semibold text-foreground">{HOST.event}</h1>
            </div>
          </div>

          <ul className="flex flex-col gap-3 text-sm text-muted">
            <li className="flex items-center gap-3">
              <Icon path={ICONS.clock} /> {HOST.duration}
            </li>
            <li className="flex items-center gap-3">
              <Icon path={ICONS.video} /> {HOST.location}
            </li>
          </ul>

          <p className="text-sm leading-relaxed text-muted">{HOST.description}</p>
        </aside>

        {/* Date + time selection */}
        <section className="p-8">
          <div className="mb-6 flex items-center gap-3">
            <Icon path={ICONS.calendar} />
            <h2 className="text-sm font-medium tracking-wide text-foreground">
              June 2026 — select a time
            </h2>
          </div>

          <div className="grid gap-8 sm:grid-cols-[1fr_minmax(0,11rem)]">
            {/* Week strip */}
            <div>
              <div className="mb-2 grid grid-cols-7 text-center text-xs text-muted">
                {["M", "T", "W", "T", "F", "S", "S"].map((l, i) => (
                  <span key={i}>{l}</span>
                ))}
              </div>
              <div className="grid grid-cols-7 gap-1.5">
                {DAYS.map((day) => (
                  <button
                    key={day.d}
                    type="button"
                    disabled={!day.available}
                    aria-pressed={day.selected}
                    className={[
                      "aspect-square rounded-lg border text-sm font-medium transition",
                      day.selected
                        ? "border-accent bg-accent text-accent-ink shadow-[0_0_18px_rgba(0,240,255,0.45)]"
                        : day.available
                          ? "border-border-strong text-foreground hover:border-accent hover:text-accent hover:shadow-[0_0_14px_rgba(0,240,255,0.25)]"
                          : "border-transparent text-muted/40",
                    ].join(" ")}
                  >
                    {day.d}
                  </button>
                ))}
              </div>
            </div>

            {/* Time slots */}
            <div className="flex max-h-72 flex-col gap-2 overflow-y-auto pr-1">
              {SLOTS.map((slot, i) => (
                <button
                  key={slot}
                  type="button"
                  className={[
                    "rounded-lg border px-4 py-2.5 text-sm font-medium transition",
                    i === 3
                      ? "border-accent bg-accent text-accent-ink shadow-[0_0_18px_rgba(0,240,255,0.45)]"
                      : "border-border-strong text-foreground hover:border-accent hover:text-accent hover:shadow-[0_0_14px_rgba(0,240,255,0.25)]",
                  ].join(" ")}
                >
                  {slot}
                </button>
              ))}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
