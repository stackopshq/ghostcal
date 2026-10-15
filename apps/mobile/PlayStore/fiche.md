# Google Play listing — GhostCal

Store copy for the Android app (`ch.stackops.ghostcal`), French and English. Every claim
was checked against `apps/mobile/lib/` on 2026-10-15; keep it that way when editing.

## Assets

| File | Play Console slot | Size |
|---|---|---|
| `visuels/icone-512.png` | App icon | 512 × 512 |
| `visuels/banniere-fr-1024x500.png` / `visuels/banniere-en-1024x500.png` | Feature graphic (per language) | 1024 × 500 |
| `captures-fr/0*.png` / `captures-en/0*.png` | Phone screenshots, in this order | 1080 × 2160 |

The screenshots come from a Redmi Note 9S (1080 × 2400) with the status and navigation
bars cropped: Play refuses a long side over twice the short side (2400 / 1080 = 2.22).
Order: day, week, month, quick entry, tasks, meeting detail, booking links, dark theme.

They show the local bench's showcase account (`tools/banc-local.sh --vitrine` data). The
event titles are French in both sets: they are the account's data, not the interface.

## Short description (80 characters max)

- FR: `Agenda chiffré de bout en bout : rendez-vous, tâches et sondages privés.`
- EN: `End-to-end encrypted calendar: private bookings, tasks and polls.`

## Full description — FR

GhostCal est un agenda dont le contenu est chiffré sur votre téléphone : le titre, le lieu
et la description de vos événements, vos tâches et ce que vos invités vous écrivent sont
illisibles pour le serveur. Il ne sait que **quand** vous êtes occupé, jamais **ce que**
vous faites.

- **Votre agenda, comme vous aimez le lire** : jour, semaine, mois ou liste, aux couleurs
  de vos calendriers, avec les rendez-vous simultanés côte à côte.
- **Saisie rapide** : « Déjeuner avec Camille demain 12h30 au Café du Marché » remplit
  l'événement tout seul, en français comme en anglais.
- **Prise de rendez-vous** : créez vos types de rendez-vous, réglez vos disponibilités,
  partagez votre lien, envoyez le lien de visio à l'invité.
- **Sondages de date** : proposez des créneaux, laissez voter sans compte, retenez le gagnant.
- **Tâches** avec échéances, **équipe** avec invitation chiffrée.
- **Ouverture par l'empreinte**, verrouillage automatique, thème clair ou sombre,
  français ou anglais.

GhostCal se connecte à un serveur GhostCal : celui de StackOps ou le vôtre, auto-hébergé.

## Full description — EN

GhostCal is a calendar whose content is encrypted on your phone: event titles, places and
notes, your tasks and what your invitees tell you are unreadable to the server. It only
knows **when** you are busy, never **what** you are doing.

- **Your calendar, the way you read it**: day, week, month or list, in your calendars'
  colours, with overlapping meetings side by side.
- **Quick entry**: "Lunch with Sam tomorrow 12:30pm at the Café" fills the event for you,
  in English or French.
- **Booking pages**: create meeting types, set your availability, share your link, send the
  video link to your invitee.
- **Date polls**: offer slots, let people vote without an account, pick the winner.
- **Tasks** with due dates, **teams** with encrypted invitations.
- **Fingerprint unlock**, auto-lock, light or dark theme, English or French.

GhostCal connects to a GhostCal server: StackOps' or your own, self-hosted.

## Regenerating

The device scripts used on 2026-10-15 drive a phone over `adb` against the local bench;
they are not versioned (they depend on one device's coordinates). The procedure: run
`tools/banc-local.sh --vitrine`, install a profile build, sign in, set the language, then
capture each screen with `adb exec-out screencap -p` and crop 100 px top / 140 px bottom.
