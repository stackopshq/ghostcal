# GhostCal apps

The GhostCal client for **Android**, **iPhone and iPad**, and **macOS**: one Flutter code base, with
the suite's [`ghost-crypto`](https://github.com/stackopshq/ghostsuite) core compiled natively
through `flutter_rust_bridge` (`rust/`). Event, task and invitee content is sealed and opened on
the device; the server only ever sees ciphertext and times. See the [main README](../../README.md)
for what the server can and cannot read.

## What

- Agenda by day, week, month (compact with a day list, or expanded with titles — a handle switches)
  and list, with tasks among the days and a red now-line.
- Quick entry (English and French), events, tasks, booking types and their questions, availability,
  polls, meetings, team invitations, profile and avatar.
- On-device search over a year of the calendar; calendar filter.
- Face ID / Touch ID / fingerprint unlock with a hardware-sealed key; auto-lock.
- Opt-in booking reminders computed on the device (Android: WorkManager; iOS: scheduled at each
  opening; macOS: notification centre, optional launch at login), neutral text, no push service.
- Keyboard shortcuts on every platform with a keyboard (⌘ on Apple, Ctrl elsewhere) and the macOS
  menu bar, both through one command path (`lib/ecrans/accueil.dart`).
- English and French; light and dark themes.

Not yet: offline access, recurring events and attendees, sign-up and password changes (web only).

App id `ch.stackops.ghostcal` everywhere. Minimum: Android 7 (API 24), iOS 15, macOS 12.

## Run

Flutter 3.47 and a Rust toolchain (the crypto core builds with the app). The core's crate is
expected at `../../../../suite/crates/ghost-crypto` relative to `rust/` — check out
[ghostsuite](https://github.com/stackopshq/ghostsuite) next to this repository accordingly.

```sh
flutter pub get
flutter run                      # a device or simulator; asks for the server address
```

Debug and profile builds accept `http://localhost` only, for a local API on port 8000
(`adb reverse tcp:8000 tcp:8000` on Android). Release builds require `https`.

## Test

```sh
flutter analyze
flutter test                     # unit and widget tests, no device needed
```

`integration_test/` drives a real build against a local server: `macos_test.dart` on macOS,
`apparence_ios_test.dart` and `banc_ios_test.dart` on an iOS simulator, `captures_test.dart` for the
store screenshots. They wait for the `accueil.pret` key and walk the app through the bottom bar's
menu (`accueil.menu`).

## Build and release

- **Android**: `flutter build appbundle --release` for Google Play, `flutter build apk --release
  --split-per-abi` for a direct download. Signing reads `android/key.properties` (not versioned);
  the upload key is kept in OpenBao.
- **iOS**: see [docs/appstore.md](../../docs/appstore.md) and `AppStore/fiche.md`.
- **macOS**: Developer ID, notarised and stapled DMG — see [docs/macos.md](../../docs/macos.md)
  (`macos/ExportOptions.plist`).
- Store copy and screenshots: `PlayStore/` and `AppStore/`.

Releases are published with their files and `SHA256SUMS` under the `mobile-vX.Y.Z` tags, on the
forge and on the [GitHub mirror](https://github.com/stackopshq/ghostcal/releases).

## Architecture

- `lib/ecrans/` — screens (`accueil.dart` holds the bottom bar, the menu and the shortcuts;
  `agenda*.dart` the calendar views).
- `lib/services/` — API client, session and vault, agenda, tasks, reminders, biometrics.
- `lib/outils/` — pure helpers (dates, quick-entry parser, lane layout).
- `lib/l10n/` — `app_fr.arb` and `app_en.arb`; generated code in `lib/l10n/generated/`.
- `rust/` — the bridge to `ghost-crypto`.
