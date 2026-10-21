# Distribuer GhostCal pour macOS

Hors Mac App Store : signature Developer ID, notarisation chez Apple, image disque
téléchargée depuis le site. Ce qui est fait dans le dépôt, ce qui reste à faire ailleurs,
et ce qui a été **mesuré** plutôt que supposé.

Le modèle est `docs/appstore.md`, qui décrit l'autre chemin — celui d'iOS, qui passe par
Apple. Ce qui diffère ici est signalé, parce que c'est ce qui se recopie de travers.

## Ce qui est fait dans le dépôt

**`apps/mobile/macos/Runner/*.entitlements`** — les trois droits qui manquaient au gabarit
de `flutter create`, et dont aucun ne produit d'erreur de compilation : sortie réseau,
groupe d'accès au trousseau, lecture du fichier choisi. Le détail et la cause de chacun
sont dans `Release.entitlements`, à l'endroit où on les lira.

**`ENABLE_HARDENED_RUNTIME = YES`**, en Release seulement. La notarisation refuse un
binaire sans durcissement ; le Debug, lui, a besoin des pages exécutables que le
durcissement interdirait. Vérifié sur le paquet construit : `codesign -dvvv` rend
`flags=0x10000(runtime)`.

**`PRODUCT_NAME = GhostCal`** — le paquet s'appelle `GhostCal.app`. C'est ce nom que le
Finder affiche après le téléchargement ; `ghostcal` aurait l'air d'un binaire tombé d'un
dépôt.

**`macos/Runner/{en,fr}.lproj/MainMenu.strings`** — les menus d'AppKit dans les deux
langues du produit. Les clés sont les identifiants d'objet du xib, extraits par
`ibtool --generate-strings-file`.

**`macos/Runner/PrivacyInfo.xcprivacy`** — repris d'iOS. **Rien ne l'exige ici** : le
manifeste est une obligation de l'App Store, pas de la distribution directe. Il est écrit
quand même, pour les raisons données dans son propre en-tête.

**`integration_test/macos_test.dart`** — la campagne qui fait tourner l'application sur la
machine, contre un vrai serveur, et mesure ce qu'aucun témoin hors matériel ne peut dire.
Voir « Ce qui a été vérifié ».

## Ce qui manque, et c'est une seule chose

**Il n'y a pas de certificat « Developer ID Application » sur cette machine.**

```
$ security find-identity -v -p codesigning
  1) … "Apple Development: clara@stackops.ch (RJ29WBG4US)"
  2) … "Apple Development: Clara Vanacker (W2P4BU4H3S)"
     2 valid identities found
```

Conséquence directe, et elle n'est pas cosmétique : `flutter build macos --release`
produit un paquet signé **en développement**, qui porte
`com.apple.security.get-task-allow`. Relevé sur le paquet construit le 2026-10-15 :

```
$ codesign -d --entitlements - --xml GhostCal.app | plutil -convert xml1 -o - -
    …
    <key>com.apple.security.get-task-allow</key>
    <true/>
```

Ce droit autorise un débogueur à s'attacher au processus. **La notarisation le refuse**,
et le refus arrive après l'envoi, dans un rapport JSON. Un paquet qui se construit, se
signe, se vérifie et ne se notarise pas : c'est exactement le genre d'écart qu'on ne voit
qu'au bout de la chaîne.

`spctl` le dit déjà, sans rien envoyer :

```
$ spctl -a -vvv -t exec GhostCal.app
GhostCal.app: rejected
origin=Apple Development: Clara Vanacker (W2P4BU4H3S)
```

C'est le comportement attendu d'un paquet de développement, pas un défaut du projet. La
signature Developer ID ne se pose **pas** par `flutter build` : elle se pose à
l'exportation d'une archive, qui re-signe tout et laisse `get-task-allow` derrière.

## La marche à suivre, pour Kevin

Rien de ce qui suit n'a été exécuté. Chaque étape dit ce qu'elle produit et comment on
voit qu'elle a marché.

### 1 · Le certificat

Dans Xcode, **Settings › Accounts › Manage Certificates › + › Developer ID Application**,
avec un compte ayant le rôle *Account Holder* ou *Admin* sur l'équipe 9WHCJ5W7S6. Un rôle
*Developer* ne peut pas en créer, et l'interface ne le dit pas : le bouton est simplement
absent.

À vérifier avant de continuer :

```sh
security find-identity -v -p codesigning | grep "Developer ID Application"
```

### 2 · Le mot de passe d'application, pour notarytool

`notarytool` n'accepte pas le mot de passe du compte Apple. Il faut un **mot de passe pour
application**, créé sur <https://account.apple.com> › Connexion et sécurité. Rangé une
fois dans le trousseau, il n'est plus jamais retapé :

```sh
xcrun notarytool store-credentials "ghostcal-notarisation" \
  --apple-id "<l'identifiant Apple de l'équipe>" \
  --team-id 9WHCJ5W7S6 \
  --password "<le mot de passe pour application>"
```

### 3 · L'archive, puis l'exportation en Developer ID

C'est l'exportation qui re-signe, et c'est elle qui retire `get-task-allow`.

```sh
cd apps/mobile
flutter build macos --release          # prépare l'assemblage Flutter et le cœur Rust

xcodebuild -workspace macos/Runner.xcworkspace -scheme Runner \
  -configuration Release -destination 'generic/platform=macOS' \
  -archivePath build/GhostCal.xcarchive archive

xcodebuild -exportArchive \
  -archivePath build/GhostCal.xcarchive \
  -exportOptionsPlist macos/ExportOptions.plist \
  -exportPath build/export
```

`macos/ExportOptions.plist` existe désormais, et porte son propre commentaire. Deux clés
y méritent une relecture avant toute modification :

`teamID` **écrite** et non découverte, pour le motif donné dans `docs/appstore.md` : un
certificat d'équipe personnelle cohabite dans le trousseau de cette machine, et la
signature automatique peut le choisir sans rien dire.

`destination` à `export`, qui n'est pas cosmétique : sans elle, `xcodebuild
-exportArchive` en `developer-id` **peut notariser de lui-même** selon la version de
Xcode. Une commande qui dit « exporter » enverrait le paquet chez Apple sans que personne
l'ait décidé. L'envoi est une étape à part, et elle a son moment plus bas.

Le contrôle qui compte, avant d'envoyer quoi que ce soit :

```sh
codesign -d --entitlements - --xml build/export/GhostCal.app \
  | plutil -convert xml1 -o - - | grep get-task-allow    # doit ne RIEN rendre
codesign -dvvv build/export/GhostCal.app 2>&1 | grep -E "Authority|flags"
#   Authority=Developer ID Application: … (9WHCJ5W7S6)
#   flags=0x10000(runtime)
```

### 4 · L'image disque

L'objet qu'on télécharge. `hdiutil` seul suffit ; `create-dmg` (Homebrew) ajoute le fond
et la flèche vers *Applications*, qui ne changent rien à la sécurité et beaucoup à la
première impression.

```sh
mkdir -p build/dmg && cp -R build/export/GhostCal.app build/dmg/
ln -s /Applications build/dmg/Applications
hdiutil create -volname GhostCal -srcfolder build/dmg -ov -format UDZO \
  build/GhostCal-1.2.0.dmg
```

**L'image doit être signée elle aussi**, sans quoi Gatekeeper la refuse avant même
d'ouvrir ce qu'elle contient :

```sh
codesign --sign "Developer ID Application: … (9WHCJ5W7S6)" \
  --timestamp build/GhostCal-1.2.0.dmg
```

### 5 · La notarisation

C'est l'étape qui part chez Apple. Quelques minutes en général.

Deux façons de s'authentifier, et la seconde est celle qui a servi : un mot de passe
d'application rangé par `notarytool store-credentials` sous un nom de profil, **ou** la
clé API App Store Connect que porte déjà cette machine pour l'envoi iOS. La seconde évite
de créer un second secret pour la même machine.

```sh
xcrun notarytool submit build/dmg/GhostCal-1.4.0.dmg \
  --key ~/.appstoreconnect/private_keys/AuthKey_<ID>.p8 \
  --key-id <ID> \
  --issuer <UUID d'équipe, en clair dans App Store Connect> \
  --wait
```

L'identifiant d'émetteur ne se déduit pas de la clé : c'est la revendication `iss` du
jeton qu'il faut justement signer. Il s'affiche dans App Store Connect, au-dessus du
tableau des clés.

En cas de refus, le rapport nomme la cause, et il faut le demander — le message de
`submit` ne la donne pas :

```sh
xcrun notarytool log <l-identifiant-de-soumission> \
  --keychain-profile "ghostcal-notarisation"
```

### 6 · L'agrafage, et pourquoi il n'est pas facultatif

**Il faut agrafer les deux : l'image, et l'application qu'elle contient.** Agrafer la
seule image ne suffit pas, et le défaut est invisible sur la machine qui a notarisé.

```sh
xcrun stapler staple build/export/GhostCal.app     # le billet existe déjà, voir plus bas
xcrun stapler staple build/dmg/GhostCal-1.4.0.dmg
xcrun stapler validate build/dmg/GhostCal-1.4.0.dmg
```

Mesuré le 2026-10-20 : image agrafée, `spctl` l'accepte, et l'application **à
l'intérieur** répondait `GhostCal.app does not have a ticket stapled to it`. Le billet de
l'image ne voyage pas avec l'application qu'on en glisse vers *Applications* : une fois
sortie, elle n'a plus rien de local, et son premier lancement redemande le réseau — ce
qu'on ne voit jamais ici, puisque la machine qui notarise a toujours du réseau.

L'ordre coûte un envoi de plus, et il n'y a pas moyen de l'éviter : l'image change quand
on y remplace l'application, donc elle doit être resignée et renotariée.

1. notariser l'image (l'application qu'elle contient reçoit son billet au passage) ;
2. `stapler staple` sur **l'application** — le billet est déjà émis pour son empreinte,
   donc l'agrafe se pose sans réenvoi ;
3. refabriquer l'image autour de l'application agrafée ;
4. resigner l'image, la renotariser, l'agrafer.

Le contrôle final porte sur les deux, et sur l'application montée depuis l'image :

```sh
xcrun stapler validate build/dmg/GhostCal-1.4.0.dmg
spctl -a -vvv -t install build/dmg/GhostCal-1.4.0.dmg
PT=$(hdiutil attach -nobrowse -readonly build/dmg/GhostCal-1.4.0.dmg | grep -oE '/Volumes/.*')
xcrun stapler validate "$PT/GhostCal.app"
spctl -a -vvv -t exec "$PT/GhostCal.app"
hdiutil detach "$PT"
```

Sans agrafage, l'image marche quand même — **tant que la machine qui l'ouvre a du
réseau**. Gatekeeper interroge alors Apple pour savoir si le paquet est notarié. Hors
ligne, ou derrière un pare-feu d'entreprise, il n'obtient pas de réponse et refuse. Agrafer
colle le billet sur l'image : la vérification devient locale.

### 7 · Le contrôle final, sur une machine qui n'a pas servi à construire

```sh
spctl -a -vvv -t install build/GhostCal-1.2.0.dmg   # accepted, source=Notarized Developer ID
```

Sur la machine de construction, le résultat est flatteur et ne prouve rien : le certificat
de développement y est. **Le seul contrôle qui vaille** est une machine propre — ou au
minimum un compte utilisateur neuf —, et un téléchargement par le navigateur, qui pose
l'attribut de quarantaine. Un fichier copié par clé USB ou par `scp` ne le porte pas, et
franchit Gatekeeper sans être examiné.

## Ce que le site doit servir

- l'image disque agrafée ;
- le numéro de version, lisible sans télécharger ;
- la somme SHA-256, pour qui veut vérifier. `shasum -a 256 build/GhostCal-1.2.0.dmg`.

**Et rien avant que le web qui lit le format `v:1` soit en production.** L'application
macOS écrit ses enveloppes en `v:1` — vérifié sur les octets rendus par le serveur, voir
ci-dessous. Le web actuellement déployé ne les lit pas : un événement créé depuis le Mac
s'afficherait illisible dans le navigateur. La version du web qui corrige cela est la
#176 ; tant qu'elle n'est pas déployée, l'image disque ne se met pas en ligne.

## La notarisation du 2026-10-20

Faite, et vérifiée. `GhostCal 1.4.0 (5)`, universelle (`x86_64 arm64`), depuis `b5e2846`.

| | |
|---|---|
| Envoi de l'image | `f49a440d-bfa9-4caa-93bb-ad0d8ce6c2cc` — **Accepted** |
| Envoi de l'image refabriquée autour de l'application agrafée | `3a96acfd-3698-4122-a34b-4f6cd125e243` — **Accepted** |
| `spctl -t install` sur l'image | `accepted`, `source=Notarized Developer ID` |
| `spctl -t exec` sur l'application montée | `accepted`, `source=Notarized Developer ID` |
| `stapler validate` | passe sur l'image **et** sur l'application |
| Droits portés | `app-sandbox`, `network.client`, `files.user-selected.read-only`, `keychain-access-groups` — et **pas** `network.server`, qui reste au Debug |
| `get-task-allow` | absent |
| Démarrage | l'application signée s'ouvre, barre de menus complète, fenêtre peuplée — interrogée par `System Events` |

Ce qui a débloqué l'export : l'ACL de la clé privée n'accordait pas l'accès à `codesign`,
et aucune interface ne le demandait — d'où un `errSecInternalComponent` opaque. Le geste
est dans Trousseaux d'accès, catégorie *Clés*, sur la clé privée du certificat Developer
ID : ⌘I → **Contrôle d'accès** → « Toujours autoriser ». Le vérifier plutôt que de
conclure sur une signature qui passe : une invite acceptée **une seule fois** donne le
même résultat et rouvrira au prochain export. Le contrôle est qu'une seconde signature
passe sans invite.

**L'image n'est pas distribuée.** La condition posée tient : rien ne se met en ligne avant
que le web qui lit le format `v:1` soit en production (#176).

## Ce qui a été vérifié, et comment

Campagne du 2026-10-15, `flutter test integration_test/macos_test.dart -d macos` contre
`tools/banc-local.sh`. Six témoins, tous verts.

| Ce qui est mesuré | Comment |
|---|---|
| Le coffre s'ouvre à la phrase | L'écran d'accueil paraît ; sinon le témoin échoue au lieu de continuer |
| Une enveloppe du web d'avant la migration se lit | Déposée par `tools/enveloppe-heritee.py` au format hérité (AES-256-GCM, nonce de 12 octets, pas de `v`), elle s'affiche à son titre et non « Contenu illisible ». Le script réimplémente l'ancien format — le cœur ne sait plus l'écrire — et se **vérifie d'abord** contre le vecteur WebCrypto de `legacy_web.rs`. À relancer après chaque `banc-local.sh` |
| Ce que le Mac écrit porte `v: 1` | Relu dans les octets rendus par le serveur, puis rouvert par l'application elle-même |
| Une question à choix obligatoire survit à l'aller-retour | `type`, `required` et `options` relus un à un |
| Une photo HEIC devient un JPEG d'au plus 1024 points | Passée par le canal natif, décodée pour en mesurer les côtés, téléversée, relue depuis le serveur, retirée |
| Le trousseau accepte une phrase sous contrainte matérielle | `retenir` rend `true` — donc le groupe d'accès est accordé —, et l'interrogation de présence répond en moins de trois secondes, donc sans invite |
| Les écrans en clair et en sombre, en français et en anglais, en petite et en grande fenêtre | Huit captures, extraites par `tools/macos/extraire-captures.py` |
| Une bannière de rappel paraît | **À la main**, par Clara, le 2026-10-20 : réglage allumé, autorisation accordée, réservation prise depuis la page publique, bannière reçue à l'heure dite. L'alerte d'autorisation et la bannière attendent l'une un clic, l'autre son heure — aucun témoin ne les atteint |
| L'ouverture du coffre par Touch ID | **À la main**, par Clara, le 2026-10-20 sur l'application installée dans `/Applications` : cocher « Ouvrir avec Touch ID », verrouiller, rouvrir, poser le doigt. Aucun témoin ne peut le faire — c'est le propre d'une biométrie |
| L'inscription aux ouvertures de session | Posée, relue **auprès du système**, puis remise comme elle était — un témoin n'a pas à laisser une entrée dans les Réglages Système de qui l'exécute |
| Les dix raccourcis de la barre de menus | Deux moitiés, mesurées séparément. La frappe → l'envoi natif : l'envoi instrumenté, les dix équivalents déclenchés par `System Events`, **y compris sur ABC-AZERTY** — voir ci-dessous. L'envoi → l'écran : `integration_test/macos_test.dart`, qui pousse chaque commande sur le canal et relit la vue, l'ancre, l'écran de recherche et l'état du coffre |
| Les deux côtés parlent la même langue | `test/menu_macos_test.dart` compare les noms de méthode émis par le Swift à ceux traités par `accueil.dart`, dans les deux sens. Sans témoin, un item renommé d'un seul côté donne un raccourci qui ne fait rien, en silence |

### Les chiffres, sur un clavier qui n'en porte pas à cet endroit

`keyEquivalent: "1"` ne reste pas « 1 ». AppKit le traduit pour la disposition active :
sur ABC-AZERTY, l'item relit `keyEquivalent == "&"`, et la barre affiche ⌘&, ⌘É, ⌘", ⌘'
pour Jour, Semaine, Mois, Liste. C'est le bon résultat — ce sont les caractères que
portent physiquement les touches 1 à 4 ici, donc le menu annonce la frappe qu'on fait.

Et les deux frappes aboutissent : ⌘& comme ⌘1 (Maj comprise) rendent « Jour ». Vérifié en
instrumentant l'envoi, le 2026-10-20, et non déduit — il aurait été aussi facile de croire
que poser « 1 » sur un clavier français ne déclenche rien, et d'aller réécrire ce qui
marchait.

Les deux flèches ne rendent aucun `AXMenuItemCmdChar` : c'est attendu d'une touche de
fonction, dont le glyphe passe par `AXMenuItemCmdGlyph`. Elles déclenchent, mesuré de la
même façon.

### Ce que ⌘L a fait apparaître, et qui n'était pas un défaut de macOS

Verrouiller laissait l'écran du dessus affiché. `home` change bien — `EcranDeConnexion`
remplace `EcranDAccueil` dès que la session se ferme — mais les écrans ouverts par
`Navigator.push` sont empilés **au-dessus** de `home` : la recherche, le détail d'un
événement, une fiche restaient visibles, déchiffrés, par-dessus un coffre verrouillé.

Mesuré le 2026-10-20 : coffre verrouillé, `EcranDeConnexion` monté, `EcranDAccueil`
démonté, et l'écran de recherche toujours au premier plan.

Ce défaut ne venait pas du raccourci et ne concerne pas que macOS : le verrouillage
automatique au retour d'arrière-plan emprunte le même appel, sur les trois plateformes. Il
suffisait de quitter l'application en laissant un événement ouvert. ⌘L l'a seulement rendu
immédiat, donc visible. Corrigé par `_RetirerLesEcransAuVerrouillage`, dans `main.dart`,
posé au-dessus du navigateur pour survivre au changement de `home` ; le témoin
d'intégration le garde, et il était rouge avant la correction.

La fenêtre et les menus ont été interrogés sur l'application **lancée**, par
`System Events` — un témoin Flutter dimensionne la vue, pas la fenêtre d'AppKit, et ne
peut donc rien dire de la taille minimale :

```
$ osascript -e '… get {name of window 1, size of window 1}'
GhostCal, 1100, 792                    # l'ouverture par défaut : 1100 × 760 + la barre de titre

$ osascript -e '… set size of window 1 to {400, 300}'
$ osascript -e '… get size of window 1'
720, 592                               # le plancher tient : 720 × 560 + la barre de titre

$ osascript -e '… get name of menu bar items of menu bar 1'
Apple, GhostCal, Fichier, Édition, Présentation, Fenêtre, Aide

$ osascript -e '… get {name, value of attribute "AXMenuItemCmdChar"} of … "Fichier" …'
Nouvel événement, missing value, Verrouiller le coffre, N, missing value, L

$ osascript -e '… get {name, value of attribute "AXMenuItemCmdChar"} of … "Présentation" …'
Jour, Semaine, Mois, Liste, …, Aujourd'hui, Période précédente, Période suivante
&, É, ", ', …, T, , 

$ osascript -e '… get name of menu items of menu 1 of menu bar item 2 …'
À propos de GhostCal, …, Réglages…, …, Masquer GhostCal, …, Quitter GhostCal, …
```

Le cœur Rust compile pour les deux architectures de macOS, et le paquet livré les porte
toutes les deux :

```
$ lipo -info build/macos/Build/Products/Release/GhostCal.app/Contents/MacOS/GhostCal
Architectures in the fat file: … are: x86_64 arm64
```

## Ce qui n'a pas pu être vérifié

**Le texte de cette invite.** Sur Android, l'application fournit les trois libellés et ils
viennent des traductions. Sur macOS, c'est le trousseau qui compose l'alerte, et
`flutter_secure_storage` n'expose pas `kSecUseOperationPrompt` : le système emploie sa
formulation par défaut, dans **sa** langue, avec le nom du produit — `CFBundleDisplayName`,
soit « GhostCal ». C'est une limite du greffon, pas un oubli. Les textes de l'application
autour de l'invite, eux, sont bien dans les deux langues (capture
`04-entree-en-sombre-petite` : « Open with Touch ID »).

**Le choix de la photo par le panneau du système.** `NSOpenPanel` n'est pas pilotable
depuis un témoin. Ce qui est éprouvé, c'est tout ce qui suit le choix — y compris le
ré-encodage, qui est la partie que macOS cassait.

**La notarisation**, évidemment : elle demande le certificat qui manque, et elle envoie
chez Apple.

## Les rappels, et ce que macOS ne permet pas

**Un piège rencontré, et qui se reproduira.** Si l'autorisation de notifier est refusée au
moment où l'on allume le réglage, `activer()` rend `false` et le réglage **reste éteint**.
La redonner ensuite dans les Réglages Système ne le rallume pas : il faut rebasculer
l'interrupteur. L'application devrait relire l'état du droit en revenant au premier plan ;
elle ne le fait pas encore.

Second piège, de la même famille : un rappel dont l'échéance est déjà passée n'est pas
programmé — c'est voulu, sans quoi tous les rendez-vous écoulés de la journée sonneraient
d'un coup au lancement. Allumer le réglage cinq minutes après l'heure du rappel ne produit
donc rien, et rien ne le dit.


Les rappels de rendez-vous sont **ceux d'Android**, `lib/services/rappels.dart`, arrivés
avec la 1.3.0. Ce portage ne les réécrit pas : il les étend. Les bannières passent des deux
côtés par `flutter_local_notifications`, et le texte — la seule partie de cette fonction
qui puisse fuir une donnée — reste là où un témoin le relit.

Ce qui diffère tient en une phrase, et elle vient de la documentation de `workmanager` :
sur macOS, les tâches de fond passent par `NSBackgroundActivityScheduler` et « run while
the app is running/backgrounded; **not after quit** ». Android réveille un téléphone
fermé ; macOS ne réveille rien.

D'où un réglage de plus, macOS seulement et éteint par défaut : **« Lancer GhostCal à
l'ouverture de session »**. L'application démarre alors **sans ouvrir de fenêtre** — le
temps de replanifier, et rien de plus. Une application de rappels qui pose un coffre
verrouillé en plein écran chaque matin se fait retirer des éléments d'ouverture avant la
fin de la semaine, en emportant les rappels avec elle.

Le coffre n'a pas à être ouvert pour cela : seules les heures de réservation sont lues, et
le serveur les détient en clair — il le doit, sans quoi il ne saurait pas refuser deux
réservations qui se chevauchent.

Sans ce réglage, les rappels ne sont replanifiés qu'à l'ouverture de l'application : une
réservation prise pendant que le Mac dort n'aura pas de bannière avant qu'on la rouvre.
C'est écrit dans le réglage plutôt que laissé à découvrir.

`SMAppService` demande macOS 13. En dessous, l'interrupteur ne s'allume pas et le dit : le
remplacement — `SMLoginItemSetEnabled` — ne vaut que pour un exécutable annexe, qu'il
faudrait écrire, signer et embarquer pour une version du système que le produit ne cible
plus guère.

Deux textes ont par ailleurs changé **des deux côtés** : ils disaient « ce téléphone » et
« les réglages du téléphone », ce qui se lit mal sur un Mac.
