import Link from "next/link";

// Minimal landing. The real booking experience lives at /{org}/{event}.
const DEMO_PATH = process.env.NEXT_PUBLIC_DEMO_PATH;

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 p-8 text-center">
      <div className="flex items-center gap-3">
        <span className="text-3xl text-accent">●</span>
        <h1 className="text-4xl font-semibold tracking-tight text-foreground">GhostCal</h1>
      </div>
      <p className="max-w-md text-muted">
        Fast, correct scheduling. Pick a time in seconds — the tool gets out of your way.
      </p>
      {DEMO_PATH && (
        <Link
          href={DEMO_PATH}
          className="rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_rgba(0,240,255,0.45)] transition hover:brightness-110"
        >
          Try the demo →
        </Link>
      )}
    </main>
  );
}
