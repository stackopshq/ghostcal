// Browser notifications for upcoming events and tasks. Unlike the content-less email reminders,
// these run in your browser — so they can show the real, decrypted title (still zero-knowledge:
// the server never sees it). Enabled per-device via the Notification permission + a local flag.

const ENABLED_KEY = "gc_notify";
const FIRED_KEY = "gc_notify_fired"; // {key: firedAtMs} — dedupe across reloads

export function notificationsSupported(): boolean {
  return typeof window !== "undefined" && "Notification" in window;
}

export function notificationsEnabled(): boolean {
  if (!notificationsSupported() || Notification.permission !== "granted") return false;
  return localStorage.getItem(ENABLED_KEY) === "1";
}

export function notificationsPermission(): NotificationPermission | "unsupported" {
  return notificationsSupported() ? Notification.permission : "unsupported";
}

/** Ask the OS for permission and turn the feature on. Returns whether it ended up enabled. */
export async function enableNotifications(): Promise<boolean> {
  if (!notificationsSupported()) return false;
  const perm =
    Notification.permission === "default" ? await Notification.requestPermission() : Notification.permission;
  if (perm === "granted") {
    localStorage.setItem(ENABLED_KEY, "1");
    return true;
  }
  return false;
}

export function disableNotifications(): void {
  localStorage.setItem(ENABLED_KEY, "0");
}

function firedMap(): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(FIRED_KEY) ?? "{}") as Record<string, number>;
  } catch {
    return {};
  }
}

/** Fire a notification once per key. Old keys are pruned so the store can't grow unbounded. */
export function notifyOnce(key: string, title: string, body: string): void {
  if (!notificationsEnabled()) return;
  const fired = firedMap();
  if (fired[key]) return;
  const dayAgo = Date.now() - 86_400_000;
  const pruned: Record<string, number> = { [key]: Date.now() };
  for (const [k, t] of Object.entries(fired)) if (t > dayAgo) pruned[k] = t;
  localStorage.setItem(FIRED_KEY, JSON.stringify(pruned));
  try {
    new Notification(title, { body, tag: key });
  } catch {
    /* ignore — the tab may be backgrounded on some browsers */
  }
}
