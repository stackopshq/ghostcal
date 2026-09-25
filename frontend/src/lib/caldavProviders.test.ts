/**
 * The two things a user cannot recover from on their own.
 *
 * A `webcal://` link pasted into the CalDAV field answered "could not reach the calendar server" —
 * true, and worthless: the server was never the problem, the field was. And nothing on the form
 * said which of the two calendar fields takes what.
 *
 * The other is worse and no error could have reached it: for iCloud there is no URL to find. Apple
 * publishes none, `https://caldav.icloud.com/` is a constant, and the form sent people looking for
 * something that does not exist. That one is fixed by the table below rather than by a message, so
 * the table is what gets tested.
 */

import { describe, expect, it } from "vitest";

import {
  CALDAV_PROVIDERS,
  connectionLabel,
  looksLikePublishedFeed,
  providerFor,
  providerIdForServer,
} from "@/lib/caldavProviders";

describe("looksLikePublishedFeed", () => {
  it("recognises what every provider's share button produces", () => {
    // This is the exact shape that was pasted in, and it must not reach the network.
    expect(
      looksLikePublishedFeed(
        "webcal://p12-caldav.icloud.com/published/2/MTA0NTQ2ODk",
      ),
    ).toBe(true);
    expect(looksLikePublishedFeed("WEBCAL://example.test/cal")).toBe(true);
  });

  it("recognises a plain file, query string and fragment included", () => {
    expect(looksLikePublishedFeed("https://example.test/basic.ics")).toBe(true);
    expect(
      looksLikePublishedFeed("https://example.test/basic.ics?token=abc"),
    ).toBe(true);
    expect(
      looksLikePublishedFeed("https://example.test/basic.ics#anchor"),
    ).toBe(true);
  });

  it("leaves a real CalDAV server alone", () => {
    for (const url of [
      "https://caldav.icloud.com/",
      "https://caldav.fastmail.com/",
      "https://cloud.example.test/remote.php/dav",
      "",
    ]) {
      expect(looksLikePublishedFeed(url), url).toBe(false);
    }
  });
});

describe("the provider table", () => {
  it("gives the hosted providers a URL, so there is nothing to look for", () => {
    expect(providerFor("icloud").serverUrl).toBe("https://caldav.icloud.com/");
    expect(providerFor("fastmail").serverUrl).toBe(
      "https://caldav.fastmail.com/",
    );
    // Not caldav.infomaniak.com, which does not resolve: /.well-known/caldav on the sync host
    // redirects to its own root, so the root is the entry point.
    expect(providerFor("infomaniak").serverUrl).toBe(
      "https://sync.infomaniak.com/",
    );
  });

  it("leaves the URL open only where it genuinely varies", () => {
    // Nextcloud is per-installation and "other" is unknown; both keep the field, with a shape.
    for (const id of ["nextcloud", "other"]) {
      const p = providerFor(id);
      expect(p.serverUrl, id).toBeNull();
      expect(p.urlTemplateKey, id).toBeTruthy();
    }
  });

  it("marks Google unsupported rather than dropping it", () => {
    // Its CalDAV needs OAuth 2.0 and the backend speaks basic auth only. Omitting it would read as
    // an oversight, and the address would be typed into "Other" — failing later and less clearly.
    const google = providerFor("google");
    expect(google.supported).toBe(false);
    expect(google.helpKey).toBeTruthy();
  });

  it("tells the user what the username is wherever a password is asked for", () => {
    for (const p of CALDAV_PROVIDERS) {
      expect(p.usernameKey, p.id).toBeTruthy();
      // Every supported provider that needs an app password must say where to get one.
      if (p.supported && p.serverUrl) expect(p.helpKey, p.id).toBeTruthy();
    }
  });

  it("falls back to a real provider rather than undefined", () => {
    expect(providerFor("does-not-exist").id).toBe(CALDAV_PROVIDERS[0].id);
  });
});

describe("naming the third party a booking is mirrored to", () => {
  it("recognises a hosted provider from its address", () => {
    expect(providerIdForServer("https://caldav.icloud.com/")).toBe("icloud");
    expect(providerIdForServer("https://sync.infomaniak.com/")).toBe(
      "infomaniak",
    );
    // Trailing path and case must not defeat it: the address is stored as the user chose it.
    expect(providerIdForServer("HTTPS://CALDAV.FASTMAIL.COM/dav/")).toBe(
      "fastmail",
    );
  });

  it("names nobody when the server is not one we know", () => {
    // A self-hosted Nextcloud belongs to someone we have never identified. Naming a company we
    // have not established would be worse than naming none — the sentence has to be true.
    expect(providerIdForServer("https://cloud.example.test/remote.php/dav")).toBeNull();
    expect(providerIdForServer("")).toBeNull();
  });

  it("shows the host and the account, never two at-signs", () => {
    // It used to render `clara@example.com@https://caldav.icloud.com/`.
    const known = connectionLabel("https://caldav.icloud.com/", "clara@example.com");
    expect(known.account).toBe("clara@example.com");
    expect(known.host).not.toContain("@");

    const unknown = connectionLabel(
      "https://cloud.example.test/remote.php/dav",
      "clara",
    );
    expect(unknown.host).toBe("cloud.example.test");
  });

  it("shows an unparseable address as typed rather than inventing one", () => {
    expect(connectionLabel("not a url", "clara").host).toBe("not a url");
  });
});

describe("the three providers added on 2026-08-31", () => {
  it("gives mailbox.org the path its discovery record points at, not the root", () => {
    // `/.well-known/caldav` on dav.mailbox.org redirects to `/caldav/`, unlike Infomaniak whose
    // record points back at its own root. Exactly the kind of detail a user cannot be asked to know.
    expect(providerFor("mailbox").serverUrl).toBe(
      "https://dav.mailbox.org/caldav/",
    );
    expect(providerFor("mailbox").supported).toBe(true);
  });

  it("marks Microsoft and Proton unsupported, and says why", () => {
    // Listed rather than omitted, for the reason Google is: an absent entry reads as an oversight,
    // and the address then gets typed into "Other", where it fails later and less clearly.
    for (const id of ["microsoft", "proton"]) {
      expect(providerFor(id).supported, id).toBe(false);
      expect(providerFor(id).helpKey, id).toBeTruthy();
      expect(providerFor(id).serverUrl, id).toBeNull();
    }
  });

  it("recognises a mailbox.org connection from its address", () => {
    expect(providerIdForServer("https://dav.mailbox.org/caldav/")).toBe(
      "mailbox",
    );
  });
});
