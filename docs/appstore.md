# Publier GhostCal sur l'App Store

Ce qui est fait dans le dépôt, ce qui reste à faire ailleurs, et pourquoi. Le modèle est
`docs/appstore.md` du dépôt GhostPass, parti chez Apple le 24 septembre 2026 ; ce qui
diffère ici est signalé, parce que c'est ce qui se recopie de travers.

## Quel projet iOS, et pourquoi la question se pose

Il existe **deux** projets iOS dans ce dépôt, portant le même nom de produit :

| Projet | Sort |
|---|---|
| `apps/ios/Ghostcal.xcodeproj` | SwiftUI. **Remplacé** par le Flutter. Ne part pas |
| `apps/mobile/ios/Runner.xcodeproj` | Celui qui part |

Se tromper donnerait une archive qui se construit, se signe, et n'est pas l'application.
Tout l'outillage de `tools/ios/` écrit le chemin en dur et le vérifie au démarrage, plutôt
que de le découvrir par un `find`.

## Fait dans le dépôt

**`apps/mobile/ios/ExportOptions.plist`** — sans lui, pas d'archive envoyable.
`app-store-connect`, et `teamID` **écrite** et non découverte : un certificat d'équipe
personnelle cohabite dans le trousseau de la machine de construction, et la signature
automatique peut le choisir sans rien dire.

**`apps/mobile/ios/Runner/PrivacyInfo.xcprivacy`** — exigé par Apple depuis mai 2024 ; sans
lui, l'envoi est refusé. Il est **câblé dans la phase « Resources » de la cible `Runner`**,
et pas seulement posé dans le dossier : la différence est mesurable, et elle a été mesurée.
Avant le câblage, `flutter build ios --release` produisait un `Runner.app` **sans** le
fichier ; après, avec. Le contrôle correspondant dans `tools/ios/archiver-appstore.sh`
regarde le paquet construit, jamais le dépôt.

Son contenu **ne recopie pas** celui de GhostPass, et c'est le point le plus important de
cette page. Voir « Ce que le serveur lit » ci-dessous.

**`tools/ios/archiver-appstore.sh`** — construit l'archive, l'exporte, et mesure ce qu'elle
contient : identifiant, famille d'appareils, version interpolée, manifeste présent, équipe
de signature, validité de la signature, absence de la déclaration de chiffrement, et
absence de vitrine. Chaque contrôle a trois issues : vert, rouge, ou « je n'ai pas pu
regarder ».

**`tools/ios/verifier-l-autonomie.sh`** — vérifie sur le **paquet livré** que l'application
ne vend rien et ne dépend d'aucune infrastructure de l'éditeur. Voir « Les instruments qui
ont menti ».

**`apps/mobile/AppStore/fiche.md`** — les textes des deux langues, les mots-clés, les
réponses au questionnaire de confidentialité, les notes d'examen, et la liste de ce qui
reste à trancher.

**Numéros de version** — `1.0.0` (build `1`), interpolés depuis `pubspec.yaml` par
`Generated.xcconfig`. Le build doit monter à chaque envoi : App Store Connect refuse deux
fois le même. `--validate-app` permet d'éprouver sans brûler de numéro.

**Déclaration de chiffrement** — la clé `ITSAppUsesNonExemptEncryption` est
**délibérément absente**, et c'est le contraire d'un renoncement. Elle vaudrait `YES`, ce
qui est vrai. Mais `YES` **sans** `ITSEncryptionExportComplianceCode` fait refuser
l'envoi — « Invalid Export Compliance Code (90592) » —, et ce code n'est délivré qu'après
examen d'une documentation qu'App Store Connect ne propose de remplir **qu'une fois un
build reçu**. La boucle ne se ferme pas. Sans la clé, les questions sont posées dans
l'interface à chaque soumission ; les réponses sont dans la fiche, tirées du code.
L'archiveur rougit si la clé réapparaît.

## Ce que le serveur lit, et pourquoi la fiche de GhostPass ne se recopie pas

GhostPass déclare une collecte minimale parce que son serveur n'héberge que des blocs
qu'il ne peut pas ouvrir. **Ce n'est pas le cas de GhostCal**, et déclarer « aucune donnée
collectée » serait faux.

Relevé dans `src/ghostcal/infrastructure/db/models.py` :

| Champ | En base | Le serveur peut-il le lire ? |
|---|---|---|
| `users.email`, `users.name`, `users.timezone` | en clair | **oui** |
| `bookings.start_at` / `end_at` | en clair | **oui** |
| `bookings.invitee_email`, `location`, `meeting_url`, `guest_emails` | `EncryptedString` | **oui** |
| `bookings.invitee_private` | scellé au X25519 de l'organisation | non |
| `users.zk_wrapped_private_key` | enveloppé sous Argon2id | non |
| Titre / lieu / description d'un événement | scellés sur l'appareil | non |

Deux choses à comprendre plutôt qu'à contourner :

1. **Les horaires sont en clair par nécessité.** La contrainte d'exclusion
   `no_overlap_per_host` — un index GiST PostgreSQL — est ce qui empêche deux réservations
   de se chevaucher. Elle travaille sur `start_at`/`end_at` : les chiffrer supprimerait la
   garantie. Les rappels par courriel ont le même besoin.

2. **`EncryptedString` n'est pas du bout en bout.** Sa docstring le dit : « a text column
   encrypted at rest with the application key ». Le serveur détient cette clé et déchiffre
   à la lecture — c'est une protection contre le vol de la base, pas une impossibilité de
   lecture. La nuance décide de la réponse au questionnaire d'Apple.

Le modèle exact de GhostCal est : **le serveur sait quand, jamais quoi** — et seulement
pour les événements et les tâches. L'application le dit elle-même à l'écran de création
d'un événement, ce qui est la bonne façon de tenir la promesse.

## Les instruments qui ont menti, le 25 septembre 2026

`tools/ios/verifier-l-autonomie.sh` est passé par quatre versions fausses avant d'être
juste. Chacune était verte ou rouge pour une mauvaise raison, et aucune n'était détectable
en la relisant. Elles sont écrites ici parce qu'elles reviendront sur le prochain outil.

1. **`strings` ne rend que de l'ASCII imprimable.** Une chaîne UTF-8 accentuée y est coupée
   à chaque accent : « Réunions » devient « R » puis « unions ». Le vocabulaire cherché
   contient « abonné », « payante », « achat intégré » : avec `strings`, ces mots n'auraient
   **jamais** pu rougir. C'est le défaut exact dont on se méfie — un contrôle qui ne sait
   pas rougir vaut moins que pas de contrôle, puisqu'on le croit.

2. **`grep -a` lit octet par octet.** Le motif de prix `[€£][0-9]` devient un jeu d'octets :
   `€` s'écrit `E2 82 AC` en UTF-8, et n'importe lequel de ces octets suivi d'un chiffre
   déclenchait une correspondance. Le contrôle rougissait sur cinq fichiers, dont un
   fichier de licences où aucun prix ne figure.

3. **`grep -ac 'Disponibilités'` rend `1` sur un binaire où ces octets sont absents.**
   Vérifié en Python : la forme UTF-8 est introuvable, la forme **Latin-1** est à l'offset
   6 264 880. Dart stocke en Latin-1 — un octet par caractère — toute chaîne dont les
   caractères tiennent sur un octet (`OneByteString`). Un contrôle qui ne décoderait qu'en
   UTF-8 ne verrait aucun mot accentué de l'application.

4. **`sort` et `sed` tronquent leur sortie** sur une séquence d'octets invalide, en ne se
   plaignant que sur stderr (« Illegal byte sequence »). Le contrôle rendait moins de
   correspondances qu'il n'en avait trouvé.

5. **`PlistBuddy` imprime pour l'œil, pas pour un script.** `Print :UIDeviceFamily` rend
   « Array { 1 2 } », et le découper donnait « Array{ 1 2 } ». Le contrôle de famille
   d'appareils rougissait sur une application parfaitement universelle : l'instrument était
   faux, pas l'objet mesuré. `plutil -extract … json` rend `[1,2]`.

Le contrôle lit désormais **trois encodages** — Latin-1, UTF-16LE aux deux alignements, et
UTF-8 — et porte un **témoin** : il cherche d'abord une chaîne accentuée que l'application
contient à coup sûr, et s'arrête si elle est introuvable, plutôt que de rendre quatre verts
sans avoir rien lu.

### Ce que l'épreuve par mutation a trouvé, et que la relecture n'aurait pas trouvé

Deux mutations, chacune injectée dans un écran, recompilée, puis retirée.

La première — « Passer a la version premium : abonnement CHF 9.90 par mois » — a fait
rougir les quatre contrôles. La seconde — **« Version payante — la facturation reprendra
en février »** — est passée sans être vue. Le contrôle était vert sur une vitrine qu'il
avait sous les yeux.

La cause : dès qu'une chaîne Dart contient un caractère au-delà de U+00FF, elle bascule en
`TwoByteString`, c'est-à-dire en UTF-16. Le tiret cadratin suffit. **Dix-neuf littéraux de
`lib/` sont dans ce cas**, dont « Contenu illisible — clé manquante ». Sans cette seconde
mutation, la faille serait passée en production du contrôle — et le contrôle aurait été
cru.

## Ce qu'une capture d'écran a trouvé et que 84 tests ne voyaient pas

Le 25 septembre, la deuxième image du jeu App Store — l'écran de création d'un
événement — est sortie sur **fond noir**, champs blancs, libellés en encre foncée à peine
lisibles.

Premier diagnostic, faux : une capture prise en pleine transition de page. L'attente est
passée de 600 ms à deux secondes ; la deuxième image était identique. Ce n'était pas la
prise de vue, c'était l'écran.

`theme.dart` pose `scaffoldBackgroundColor: Colors.transparent`, délibérément : le fond
est un dégradé et un halo peints par `FondGhost`, qu'un `Scaffold` opaque masquerait. Les
cinq onglets n'ont rien à faire, `EcranDAccueil` les enveloppant tous. Mais un écran
**poussé** par `Navigator.push` est frère de l'accueil dans la pile, pas son enfant : il
n'hérite de rien.

Quatre écrans étaient dans ce cas, dont celui du parcours principal :

| Écran | Atteint depuis |
|---|---|
| `nouvel_evenement.dart` | le « + » de l'agenda, et l'appui sur une ligne |
| `profil.dart` | Réglages > Compte > Profil |
| `sondages.dart` (deux écrans) | Réglages > Collaboration > Sondages |
| `equipe.dart` | Réglages > Collaboration > Équipe |

**Pourquoi 84 tests n'en disaient rien.** Le symptôme ne ressemble pas à la cause. En
thème clair, cela se lit comme un thème sombre mal fichu, pas comme un fond absent. Et
aucun test ne mesurait la peinture : les champs étaient présents, les boutons
réagissaient, les valeurs remontaient. Tout fonctionnait.

`test/fond_test.dart` garde désormais la propriété, en lisant le source plutôt qu'en
montant les écrans — ceux-ci n'existent qu'une fois le coffre ouvert, et un tel test
mesurerait surtout ses propres bouchons. Il porte deux gardes contre lui-même : il échoue
si `lib/ecrans` est introuvable ou contient moins de dix fichiers (le cas où il se croirait
vert sans rien avoir lu), et il vérifie que l'accueil porte bien le `FondGhost` dont
dépendent les cinq écrans qu'il dispense. Éprouvé par mutation dans les deux sens.

## À faire hors du dépôt

### Compte et identifiants

- Compte développeur Apple — équipe `9WHCJ5W7S6` (« Clara Vanacker »), la même que
  GhostPass, validée le 14 septembre 2026.
- L'identifiant `ch.stackops.ghostcal` est enregistré — créé par la signature automatique.
- **Pas d'extension, pas de groupe d'applications.** Contrairement à GhostPass, GhostCal
  n'a ni extension de remplissage ni conteneur partagé : le piège du groupe immobilisé ne
  s'applique pas ici.
- `DEVELOPMENT_TEAM` doit être **imposée** et non découverte, pour la raison écrite dans
  `ExportOptions.plist`.

### Les trois blocages de soumission, par ordre de certitude

1. **Aucune capture d'écran n'existe.** App Store Connect en réclame **deux jeux** —
   l'application se déclare universelle (`TARGETED_DEVICE_FAMILY = "1,2"`). Voir la section
   « Captures d'écran » de la fiche : la difficulté propre à GhostCal est qu'une prise de
   vue suppose un **PostgreSQL** amorcé, là où GhostPass se contentait d'un SQLite jetable.
   L'index GiST de `no_overlap_per_host` n'existe pas en SQLite.

2. **Aucune URL de confidentialité ni d'assistance.** Les deux sont obligatoires. Le dépôt
   n'a pas de brouillon de politique pour GhostCal — GhostPass a `docs/confidentialite.md`,
   GhostCal n'a pas d'équivalent — et le texte de GhostPass ne se recopie pas : les données
   collectées ne sont pas les mêmes.

3. **Aucun compte de démonstration.** L'application n'a **ni inscription ni mot de passe
   oublié** : un examinateur sans compte ne voit rien. Et un compte vide donne cinq écrans
   blancs — il doit être **amorcé** avec des événements, des tâches, une réunion réservée et
   un sondage.

### Chiffrement : deux démarches, pas une

Le cœur Rust de GhostCal — Argon2id, X25519, crypto_box — n'entre dans aucune exemption
d'Apple : ce n'est ni du HTTPS d'appoint ni de l'authentification seule. Deux conséquences,
les mêmes que pour GhostPass :

- un rapport d'auto-classification annuel auprès du **BIS** américain ;
- côté français, une **déclaration ANSSI** de fourniture d'un moyen de cryptologie.

GhostPass a rédigé `docs/anssi-dossier-technique.md`. **GhostCal n'a pas d'équivalent**, et
celui de GhostPass ne convient pas tel quel : les primitives se recoupent, mais la gestion
des clés diffère — la rotation par génération d'organisation, avec conservation des
générations antérieures pour relire l'ancien, n'existe pas chez GhostPass.

## L'archive de diffusion

Construite pour la première fois le 25 septembre 2026, en `Release`, signée par l'équipe
`9WHCJ5W7S6` :

    ./tools/ios/archiver-appstore.sh --archive    # archive seule
    ./tools/ios/archiver-appstore.sh              # archive + export

**Ce que l'archive prouve, et que rien n'avait prouvé jusque-là :**

| Vérifié sur l'archive | Résultat |
|---|---|
| Identifiant de paquet | `ch.stackops.ghostcal` |
| Famille d'appareils | `[1,2]` — iPhone et iPad |
| Version | 1.0.0 (1), interpolée |
| Manifeste de confidentialité | présent à la racine du paquet, et valide |
| Équipe de signature | `9WHCJ5W7S6`, pas l'équipe personnelle |
| Signature | `codesign --verify --deep --strict` passe |
| Déclaration de chiffrement | clé **absente** — voir plus haut |
| Vitrine, prix, point de terminaison de l'éditeur | aucun |

Une nuance sur l'identité de signature : l'archive porte « Apple **Development** : Clara
Vanacker ». C'est normal — c'est l'export qui la remplace par une identité de diffusion.
Le script le signale en jaune plutôt qu'en vert, pour que la distinction reste visible, et
tranche sur l'IPA, qui est ce qui part.

### Ce qui bloque l'export, et qui n'est pas dans le dépôt

Chez GhostPass, l'export a d'abord échoué ainsi :

    xcodebuild -exportArchive … → EXPORT FAILED
    error: No profiles for 'ch.stackops.ghostpass' were found
    error: Unable to log in with account '…'

Les profils posés par la signature automatique lors d'une installation sur iPhone sont des
profils de **développement**. L'export `app-store-connect` réclame des profils de
**distribution**, qu'Xcode crée en se connectant au compte — connexion qui échoue quand la
session a expiré ou que l'authentification à deux facteurs attend une réponse. Le remède
est de se reconnecter dans Xcode (Settings > Accounts), pas de changer le script.

### L'envoi

L'envoi réclame des identifiants qui ne sont pas — et n'ont pas à être — dans le dépôt.
Deux voies :

- **Clé API App Store Connect** : un `.p8` dans `~/.appstoreconnect/private_keys/`, plus
  l'identifiant de clé et celui de l'émetteur. C'est la voie à préférer : elle ne partage
  aucun mot de passe de compte et se révoque seule.

      xcrun altool --validate-app -f …/Runner.ipa -t ios --apiKey <ID> --apiIssuer <ISSUER>
      xcrun altool --upload-app  -f …/Runner.ipa -t ios --apiKey <ID> --apiIssuer <ISSUER>

- **Mot de passe d'application** : `--username`, `--app-password`, `--provider-public-id`.

**Valider avant d'envoyer.** `--validate-app` rend les mêmes refus que l'envoi sans
consommer de numéro de version.

## Ce qui n'est pas prêt et qu'il vaut mieux savoir

**L'application parle français et anglais**, depuis le 25 septembre 2026. GhostPass livre
les deux sur iOS comme sur Android ; GhostCal les livre désormais aussi.

*Ce qui a été fait.* Cent vingt-deux messages extraits vers `lib/l10n/app_fr.arb` et
`app_en.arb`, le français servant de modèle — c'est la langue dans laquelle le produit a
été pensé, et ses formulations sont pesées : « Contenu illisible — clé manquante » ne dit
pas la même chose que « Erreur ». Les écrans appellent `L.of(context)` ; il ne reste **zéro
littéral français** dans `lib/ecrans/`, et `test/traduction_test.dart` le mesure.

*Trois choses que la traduction a révélées, et qu'elle seule pouvait révéler.*

1. **Les composants de Flutter restaient en anglais.** Sans `flutter_localizations`, un
   iPhone réglé en français affichait « Select date », « Cancel » et des jours notés
   S M T W T F S sur l'écran de création d'événement — le parcours principal.

2. **Le repli d'une langue inconnue tombait sur l'anglais.** `gen-l10n` classe
   `supportedLocales` par ordre alphabétique : « en » précède « fr », et Flutter retient la
   première quand rien ne correspond. Ce n'était pas un choix, c'était l'alphabet. Un
   `localeResolutionCallback` explicite ramène le français, pour un produit écrit en
   français et vendu d'abord en Suisse romande.

3. **Deux énumérations portaient leur texte en constante.** `DelaiDeVerrouillage` et le
   rôle d'un membre. Elles rendent maintenant `libelle(L)` et `roleLisible(L)` : la
   correspondance reste collée aux valeurs, parce qu'un `switch` sur une énumération est
   **exhaustif** — ajouter un délai sans lui donner de libellé ne compile pas —, mais le
   texte vient des `.arb`.

*Ce qui reste, et qui est nommé.* Huit messages produits **au fond des services**, qui
n'ont pas de `BuildContext` : deux dans `auth.dart`, trois dans `biometrie.dart`, deux dans
`session.dart`, un dans `api.dart`. Les corriger demande qu'ils rendent un code que l'écran
traduirait — un chantier d'architecture, pas un remplacement de chaîne.

`test/traduction_test.dart` les **compte fichier par fichier** et échoue dans les deux sens :
si un nouveau littéral apparaît, et si l'un disparaît sans que la liste soit raccourcie.
Éprouvé par mutation dans les deux sens. Écrire « il reste quelques chaînes » dans une
documentation vieillit mal ; un test qui les nomme, non.

`untranslated-messages-file` est activé dans `l10n.yaml` : `gen-l10n` y écrirait toute clé
présente en français et absente en anglais. Sans ce réglage, la version anglaise
retomberait **en silence** sur des phrases françaises. Le fichier est vide, et
`test/langue_test.dart` échoue s'il cesse de l'être.

**Les messages d'erreur ne sont pas tous en français** : le code fait
`setState(() => _erreur = '$e')`, ce qui affiche le message brut de l'exception. Une panne
réseau affichera un texte anglais de `dart:io`.

**Aucun mode hors ligne**, aucune notification locale, aucun rappel dans l'application. La
fiche le dit ; les mots-clés l'évitent.

**Jamais éprouvé sur appareil réel pour ce projet Flutter** : il existe un dossier
`apps/mobile/ios/.build-appareil/` issu d'un build de développement, mais le parcours
complet — première connexion contre une instance distante, Face ID matériel, création d'un
événement — n'a pas été refait depuis. GhostPass a payé six défauts invisibles en
simulateur avant de s'en apercevoir.
