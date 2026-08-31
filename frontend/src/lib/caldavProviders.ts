/**
 * Where a CalDAV calendar actually lives, so nobody has to go looking for it.
 *
 * The form used to ask for a "CalDAV server URL" with a Fastmail address as the example. For iCloud
 * — the case that came up — there is nothing to find: Apple publishes no personal URL, and
 * `https://caldav.icloud.com/` is a constant, the same for every account. Asking someone to fetch a
 * value that does not exist cannot be rescued by a better error message, because the server is
 * never reached. The fix is to stop asking.
 *
 * Basic auth is the only scheme the backend speaks (`caldav.DAVClient(url, username, password)`),
 * and that decides who can be on this list.
 */

/** What the username field means differs per provider, so the form says which. */
export type CaldavProvider = {
  id: string;
  /** i18n key for the display name. */
  nameKey: string;
  /** Fixed for hosted providers; null when the user must supply it (self-hosted, or unknown). */
  serverUrl: string | null;
  /** Shown in the URL field when there is no fixed URL — a shape, not an example to copy. */
  urlTemplateKey?: string;
  /**
   * False when the provider cannot be connected this way at all. Listed anyway: an absent Google
   * reads as an oversight, and the user then types its address into "Other" and fails there
   * instead. Saying why, once, is shorter than that.
   */
  supported: boolean;
  /** i18n key for provider-specific guidance — app passwords, where to make one. */
  helpKey: string | null;
  /** i18n key describing what the username is for this provider. */
  usernameKey: string;
};

export const CALDAV_PROVIDERS: CaldavProvider[] = [
  {
    id: "icloud",
    nameKey: "cal.provider.icloud",
    serverUrl: "https://caldav.icloud.com/",
    supported: true,
    helpKey: "cal.help.icloud",
    usernameKey: "cal.user.icloud",
  },
  {
    id: "fastmail",
    nameKey: "cal.provider.fastmail",
    serverUrl: "https://caldav.fastmail.com/",
    supported: true,
    helpKey: "cal.help.fastmail",
    usernameKey: "cal.user.fastmail",
  },
  {
    id: "nextcloud",
    nameKey: "cal.provider.nextcloud",
    // Per-installation by definition, so the field stays open — but with the shape shown, which is
    // the part people actually get wrong.
    serverUrl: null,
    urlTemplateKey: "cal.tpl.nextcloud",
    supported: true,
    helpKey: "cal.help.nextcloud",
    usernameKey: "cal.user.nextcloud",
  },
  {
    id: "google",
    nameKey: "cal.provider.google",
    serverUrl: null,
    // Google's CalDAV requires OAuth 2.0; there is no password-authenticated endpoint, so no URL
    // and no app password would make this work. The form says so instead of letting it fail.
    supported: false,
    helpKey: "cal.help.google",
    usernameKey: "cal.user.other",
  },
  {
    id: "other",
    nameKey: "cal.provider.other",
    serverUrl: null,
    urlTemplateKey: "cal.tpl.other",
    supported: true,
    helpKey: null,
    usernameKey: "cal.user.other",
  },
];

export function providerFor(id: string): CaldavProvider {
  return CALDAV_PROVIDERS.find((p) => p.id === id) ?? CALDAV_PROVIDERS[0];
}

/**
 * Whether this looks like a published calendar file rather than a CalDAV server.
 *
 * Two forms of the same mistake: a `webcal://` link, which is what every provider's "share" button
 * produces, and a direct `.ics`. Both are read-only snapshots and belong in Subscriptions — where
 * `_validate_feed_url` already rewrites `webcal://` to `https://`, which means someone hit this
 * exact confusion and fixed it in the other field.
 *
 * Answering "could not reach the calendar server" here is true and worthless: the server was never
 * the problem, the field was.
 */
export function looksLikePublishedFeed(url: string): boolean {
  const value = url.trim().toLowerCase();
  if (!value) return false;
  if (value.startsWith("webcal://")) return true;
  // Strip any query string before looking at the extension: `…/basic.ics?token=…` is still a file.
  return /\.ics(\?|$)/.test(value.split("#")[0]);
}
