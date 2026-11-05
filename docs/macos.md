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

## Pourquoi `flutter build` ne suffit pas

Le certificat « Developer ID Application » est là depuis le 2026-10-20 :

```
$ security find-identity -v -p codesigning
  1) … "Apple Development: clara@stackops.ch (RJ29WBG4US)"
  2) … "Apple Development: Clara Vanacker (W2P4BU4H3S)"
  3) … "Developer ID Application: Clara Vanacker (9WHCJ5W7S6)"
     3 valid identities found
```

Mais l'avoir ne suffit pas, et c'est ce que cette section garde : `flutter build macos --release`
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

## La marche à suivre

Exécutée en entier le 2026-10-20, pour la 1.4.0 puis la 1.4.1 — voir « Les versions
notariées » plus bas. Chaque étape dit ce qu'elle produit et comment on voit qu'elle a
marché, parce que c'est ce qui manquait le plus la première fois.

### 1 · Le certificat

Dans Xcode, **Settings › Accounts › Manage Certificates › + › Developer ID Application**,
avec le compte **Account Holder** de l'équipe 9WHCJ5W7S6 — et lui seul. Ni *Admin* ni
*Developer* ne peuvent en créer, et l'interface ne le dit pas : le bouton est simplement
absent.

L'API App Store Connect ne peut pas davantage le faire, et elle le dit en clair, ce qui
est la seule fois de cette page où Apple est explicite. **Les deux types ont été
essayés**, le 2026-10-20, pour qu'on n'ait pas à se demander si l'autre aurait marché :

```
POST /v1/certificates   DEVELOPER_ID_APPLICATION_G2   → 403
POST /v1/certificates   DEVELOPER_ID_APPLICATION      → 403
« This operation can only be performed by the Account Holder »
```

Et ce n'est pas une question de droits de la clé : « titulaire du compte » est une
**personne**, pas un rôle qu'on attribue à une clé d'API. Une clé mieux dotée ne changerait
rien. Inutile donc de chercher à automatiser cette étape, ni une variante d'appel : il n'y
en a pas. Le certificat se crée à la main, dans Xcode, par cette personne-là.

À vérifier avant de continuer :

```sh
security find-identity -v -p codesigning | grep "Developer ID Application"
```

#### Celui qu'on a est un G1, et il expire le 2027-02-01

Xcode délivre un certificat signé par l'autorité **G1**, et la validité d'un certificat ne
dépasse jamais celle de son émetteur — ici à la seconde près. Relu sur la machine le
2026-10-21 :

```
$ security find-certificate -c "Developer ID Application: Clara Vanacker" -p \
    | openssl x509 -noout -issuer -enddate
issuer=CN=Developer ID Certification Authority, …, O=Apple Inc.
notAfter=Feb  1 22:12:15 2027 GMT
```

```
notre certificat   notBefore=Oct 20 09:09:52 2026   notAfter=Feb  1 22:12:15 2027
autorité G1        notBefore=Feb  1 22:12:15 2012   notAfter=Feb  1 22:12:15 2027
autorité G2        OU=G2                            notAfter=Sep 17 00:00:00 2031
```

Trois mois et demi, là où un Developer ID dure normalement cinq ans. C'est pour cela
qu'Apple a fait la G2.

Trois conséquences, et la deuxième est celle qui se paie chez les autres :

1. **On peut signer et distribuer aujourd'hui.** C'est fait : la 1.4.0 et la 1.4.1 sont
   notariées et en ligne.
2. **Il faut signer avec un horodatage sécurisé** — `--timestamp`, voir l'étape 3. Avec
   lui, ce qui est distribué continue de s'ouvrir après le 1er février 2027 : l'horodatage
   prouve que la signature était valide au moment où elle a été faite. Sans lui, **tout ce
   qui a été distribué cesse de se vérifier à cette date**, et le défaut ne se voit jamais
   sur la machine qui a signé — comme l'agrafage de l'application dans l'image.
3. **Après le 1er février 2027, plus aucune build nouvelle** ne pourra être signée avec
   celui-ci. Il faudra un G2, créé depuis `developer.apple.com` plutôt que depuis Xcode.

Rien n'oblige à le faire maintenant. Mais le jour où ce certificat expire est connu, et
c'est le genre d'échéance qu'on découvre autrement un vendredi soir.

### 2 · De quoi s'authentifier auprès de notarytool

Deux voies, et **c'est la seconde qui a servi** : elle évite de créer un second secret sur
une machine qui en porte déjà un pour l'envoi iOS.

**La clé API App Store Connect.** Si la machine en a déjà une — `~/.appstoreconnect/
private_keys/AuthKey_<ID>.p8` —, `notarytool` l'accepte directement, avec l'identifiant de
clé et celui d'émetteur. L'identifiant d'émetteur ne se déduit pas de la clé : c'est la
revendication `iss` du jeton qu'il faut justement signer, et il s'affiche en clair dans
App Store Connect, au-dessus du tableau des clés. Voir l'étape 5 pour l'invocation.

**Le mot de passe pour application.** `notarytool` n'accepte pas le mot de passe du compte
Apple. Il faut un **mot de passe pour application**, créé sur
<https://account.apple.com> › Connexion et sécurité. Rangé une fois dans le trousseau, il
n'est plus jamais retapé :

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

Il faut deux envois, mais **l'ordre décide de leur nature** : notariser l'application
d'abord, ou refaire l'image. Le second est celui qu'on trouve en tâtonnant, et c'est le
plus coûteux.

Le bon ordre — l'application part seule, dans une archive :

1. `ditto -c -k --keepParent build/export/GhostCal.app build/GhostCal-app.zip` ;
2. notariser ce `.zip` — le billet est émis pour l'empreinte de l'application ;
3. `stapler staple` sur l'application ;
4. fabriquer l'image **autour de l'application déjà agrafée** ;
5. signer l'image, la notariser, l'agrafer.

Chaque objet est notarié une fois, et rien n'est refait. L'archive ne sert qu'au transport :
on ne la distribue pas, et on ne l'agrafe pas — c'est l'application qu'elle contient qui
reçoit l'agrafe.

L'ordre inverse — notariser l'image, puis découvrir que l'application n'a pas d'agrafe —
oblige à refabriquer l'image autour de l'application agrafée, donc à la resigner et à la
renotarier, puisqu'elle a changé. C'est ce qui a été fait pour la 1.4.0, avant de
comprendre. Même nombre d'envois, mais une image construite deux fois.

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

**La condition qui bloquait la mise en ligne est levée.** L'application macOS écrit ses
enveloppes en `v:1`, et le web qui les lit (#176) est en production depuis le 2026-10-15 ;
un événement créé depuis le Mac s'ouvre donc dans le navigateur. Ce qui précède est resté
vrai plusieurs jours et ne l'est plus : avant la #176, un tel événement s'affichait
illisible dans le web.

L'image est jointe à la publication de `github.com/stackopshq/ghostcal`, sur l'étiquette
`mobile-vX.Y.Z`, à côté de l'AAB et de l'APK. Elle ne vit plus dans le dépôt.

### Une publication restée en brouillon ne sert rien, et le dit mal

Mesuré le 2026-11-03 sur la 1.8.1, environ trois heures après l'avoir crue publiée.

`gh release create` ayant été refusé, la publication avait été créée avec `--draft` puis
sortie du brouillon par `gh release edit --draft=false`. Ce second geste **n'a pas pris**,
et rien ne l'a signalé : l'étiquette `mobile-v1.8.1` n'existait pas, la publication
s'appelait `untagged-697b0137…`, et `Latest` désignait encore la 1.6.0.

Un actif de brouillon n'est lisible qu'**authentifié**. Depuis cette machine, qui porte un
jeton, tout avait l'air normal — c'est le défaut qui se voit le moins depuis l'endroit où
on travaille, comme l'agrafe de l'application dans l'image. Pour tout le monde :

```
$ curl -o /dev/null -w '%{http_code}' -L \
    https://github.com/stackopshq/ghostcal/releases/download/mobile-v1.8.1/GhostCal-1.8.1.dmg
404
```

Pendant ce temps, l'appcast signé était en ligne et annonçait cette adresse, et la page de
téléchargement du site pointait dessus. Donc : chaque exemplaire du parc se voyait proposer
une mise à jour qu'il ne pouvait pas récupérer, et le bouton « Télécharger pour Mac » rendait
une page d'erreur. **Notarisé, signé, annoncé, et inatteignable.**

Après `gh release edit --draft=false --latest`, l'étiquette est apparue au bon commit, mais
l'adresse a continué de rendre 404 quelques minutes : le CDN de GitHub avait mis la réponse
négative en cache. N'importe quel paramètre d'URL la contournait (`?cb=1`), ce qui permet de
distinguer ce cache d'un véritable défaut de publication.

**Le contrôle à faire, et il ne coûte rien :**

```sh
# sans jeton, comme un client — doit rendre 200 et la taille annoncée dans l'appcast
curl -s -o /tmp/verif.dmg -w '%{http_code} %{size_download}\n' -L <url nue>
shasum -a 256 /tmp/verif.dmg            # doit égaler la somme du tableau ci-dessous
spctl -a -vvv -t install /tmp/verif.dmg # accepted, source=Notarized Developer ID
```

Et sur l'entrée d'appcast, pour vérifier qu'elle parle bien de ces octets-là : la signature
Ed25519 de Sparkle est **déterministe**, donc `sign_update --account ghostcal` relancé sur le
fichier téléchargé doit rendre exactement la chaîne qui est en ligne. Fait le 2026-11-03 sur
la 1.8.1 : identique, longueur comprise.

## Les versions notariées

| Version | Source | Envois acceptés | SHA-256 de l'image |
|---|---|---|---|
| 1.8.3 (15) | `1f7b610` | `7aaf3658…` (application), `a805418d…` (image refabriquée autour d'elle) | `909560888f31aa23cd3a09c6fd4196f9de91007a5624e147e9f6bd893d7868e0` |
| 1.8.2 (14) | `293dc06` | `b777ae7e…` (application), `74162c65…` (image refabriquée autour d'elle) | `b198003b44f61c6f9997adff156e103b9e64ddb7f99847eaf4160910bda7de6f` |
| 1.8.1 (13) | `86b89c6` | `d5cf2637…` (application), `be799f1a…` (image refabriquée autour d'elle) | `2208cdfd73c8d67fab33371d601d3d3b234705f098313c96e77d50d1afe2d5ce` |
| 1.6.0 (9) | non relevée | non relevés | `6c457f347d85246a620378f5ea2c650bf894f7ee0c087f2f50eb3b56ac802100` |
| 1.5.1 (8) | non relevée | non relevés | `5600afa6bf6343041236c6f038b9c80918f3bf9014631f5cb8b1dafba9324725` |
| 1.5.0 (7) | non relevée | non relevés | `7f630c87a829f52a9471eaedcfbcefa0bbf77ca0c3c4968817f32aefe37129b0` |
| 1.4.1 (6) | `0c1f6b6` | `81a324cf…` (application), `21e30a07…` (image) | `428b85efa09ab83bdf2b34222b1ae1f57609efb32e1e31139a71c900b752c255` |
| 1.4.0 (5) | `b5e2846` | `f49a440d…`, `3a96acfd…` (image construite deux fois) | `a6c372fdf463ad928686d52402c4759742a225ac01f8dfeb6be317a5ad248b80` |

Trois lignes portent « non relevée » et ce n'est pas une coquette : les 1.5.0, 1.5.1 et
1.6.0 ont été **notariées et servies** — elles sont en ligne, leurs sommes ci-dessus sont
celles des fichiers publiés — sans que personne ne les inscrive ici. Ce tableau a donc
affirmé pendant deux semaines que la dernière image distribuée était la 1.4.1. C'est faux,
et cela a faussé un diagnostic le 2026-11-03. Un tableau qu'on ne remplit pas ment, il ne
se tait pas.

Pour les 1.4.x et les 1.8.x : universelle `x86_64 arm64`, runtime durci, autorité Developer ID,
horodatage sécurisé, `get-task-allow` absent. Les agrafes valides, et `spctl` accepte
l'image **et** l'application montée depuis l'image.

Les droits ne sont plus les mêmes des deux côtés de la 1.6.0, et le relevé ci-dessus vaut
pour la version en face : les 1.4.x portent `app-sandbox`, `network.client`,
`files.user-selected.read-only` et `keychain-access-groups` ; la 1.8.1 y ajoute
`temporary-exception.mach-lookup.global-name`, pour les deux noms que Sparkle impose. Le
motif est dans `Release.entitlements`, à l'endroit où on le lira.

Les images ne vivent plus dans le dépôt. Elles sont jointes aux publications de
`github.com/stackopshq/ghostcal`, sur l'étiquette `mobile-vX.Y.Z` — et c'est de là que le
flux Sparkle les sert, pas depuis le Gitea. Les cinq publiées y sont, de la 1.4.0 à la
1.6.0.

## La notarisation du 2026-11-04, et la panne qu'elle répare

`GhostCal 1.8.3 (15)`, depuis `1f7b610`. Faite le soir même où l'on a découvert que
**aucune installation macOS n'avait jamais pu se mettre à jour seule**.

### Le défaut : une clé d'Info.plist, et la moitié d'une page lue

L'application est dans le bac à sable. Sparkle exige alors
`SUEnableInstallerLauncherService` pour faire passer l'installation par son service XPC
`Installer.xpc`, qui travaille **hors** du bac à sable — il faut bien remplacer un paquet
dans `/Applications`. La clé n'a jamais été écrite. Sparkle tentait donc le lancement
direct, le bac à sable le refusait, et l'utilisateur lisait :

> An error occurred while launching the installer. Please try again later.

Les deux exceptions `mach-lookup` de `Release.entitlements`
(`$(PRODUCT_BUNDLE_IDENTIFIER)-spks` et `-spki`) étaient là **depuis la 1.6.0** : c'est
l'autre moitié de la même exigence, et elle seule avait été posée. Les droits promettaient
le chemin XPC que la clé n'ouvrait pas. C'est le genre d'écart qu'aucune compilation ne
signale et qu'aucun témoin hors matériel ne voit.

Relevé sur les trois images réellement servies : **la 1.6.0, la 1.8.1 et la 1.8.2 en sont
toutes dépourvues.** La panne est restée invisible deux semaines parce qu'**aucune entrée
d'appcast n'a été servie après la 1.6.0** : le chemin d'installation n'avait jamais tourné
une seule fois. Il a tourné le 2026-11-03 au soir, sur l'écran de Clara, et il a cassé.

### Ce que cette panne impose, et qui ne se rattrape pas

**C'est l'application déjà installée qui installe.** Donc une version corrigée ne peut pas
arriver par la mise à jour automatique : le réparateur est la pièce cassée. Tout le parc
doit retélécharger **une fois** à la main. Les deux pages de téléchargement le disent
désormais au-dessus du tableau, et c'est le dernier téléchargement manuel.

### Ce qui a été mesuré, et ce qui ne l'a pas été

**Essai positif, concluant.** Une paire 1.8.3 / 1.8.4 construite avec la clé, sur un
identifiant de paquet et un flux d'essai isolés — pour ne pas approcher une installation
réelle ni son conteneur. Appcast local sur `127.0.0.1`. Le paquet dans `/Applications` est
passé de 1.8.3 à **1.8.4 tout seul**, et le journal système montre la chaîne entière :

```
org.sparkle-project.InstallerLauncher
processus Installer
ch.stackops.ghostcal.essai-spki
processus Autoupdate
```

**Témoin négatif, NON concluant.** Deux tentatives sur le même binaire privé de la seule
clé et re-signé : Sparkle n'a jamais reproposé la mise à jour, donc il n'a jamais tenté de
l'installer, et la panne n'a pas été reproduite en labo. Le conteneur de bac à sable, qui
retient l'heure du dernier contrôle, est protégé par le système et ne se remet pas à zéro
depuis un terminal. La panne reste donc attestée par l'écran d'un utilisateur et par la
documentation de Sparkle — **pas** par un banc. C'est écrit ici pour que personne ne croie
la symétrie acquise.

| | |
|---|---|
| Envoi de l'application | `7aaf3658-0552-4a60-a939-bba94a5b62d6` — **Accepted** |
| Envoi de l'image refabriquée autour de l'application agrafée | `a805418d-f6af-4332-9bba-becedd1dab96` — **Accepted** |
| `spctl -t install` sur l'image | `accepted`, `source=Notarized Developer ID` |
| `spctl -t exec` sur l'application montée | `accepted`, `source=Notarized Developer ID` |
| `stapler validate` | passe sur l'image **et** sur l'application |
| `get-task-allow` | absent |
| Architectures | `x86_64 arm64` |
| Horodatage de l'image | `4 Nov 2026 at 21:51:35` |
| `SUEnableInstallerLauncherService` | `true`, relue sur l'application **montée depuis l'image** |

Cette dernière ligne est un garde-fou du script de notarisation, pas une coquetterie : il
s'arrête si la clé manque ou n'est pas à `true`. Publier une 1.8.3 qui ne corrige rien
serait pire que de n'avoir rien publié, puisque chacun aurait retéléchargé pour rien.

## La seconde notarisation du 2026-11-03

`GhostCal 1.8.2 (14)`, depuis `293dc06`, soit `main` sans rien de plus. Faite le soir même
que la 1.8.1, et pour la suite du même retour client : la 1.8.1 lui a rendu la suppression
d'un calendrier et ses abonnements ICS, la 1.8.2 lui rend la **troisième** source, celle
qu'il nommait en premier — « je ne vois pas mes calendriers externes ». Les comptes
connectés depuis le web, CalDAV, iCloud et Google, n'avaient jamais eu leur ligne dans la
colonne, à aucune version et sur aucune plateforme.

| | |
|---|---|
| Envoi de l'application | `b777ae7e-ea19-4137-b458-85b04a8e8853` — **Accepted** |
| Envoi de l'image refabriquée autour de l'application agrafée | `74162c65-7377-4c00-ac17-7c4c78248902` — **Accepted** |
| `spctl -t install` sur l'image | `accepted`, `source=Notarized Developer ID` |
| `spctl -t exec` sur l'application montée | `accepted`, `source=Notarized Developer ID` |
| `stapler validate` | passe sur l'image **et** sur l'application |
| `get-task-allow` | absent |
| Architectures | `x86_64 arm64` |
| Horodatage de l'image | `3 Nov 2026 at 23:37:04` |
| Flux et clé compilés dans le paquet | `ghostsuite.cloud/ghostcal/appcast.xml`, `0k3dHuuuNoGUtcccykg+oeFRfsLqcQ1cx4csQfqj5j0=` |

Le script s'est terminé en erreur (code 16) **après** tous ces contrôles : `hdiutil detach`
a rendu « Ressource occupée » sur le volume de vérification, une archive iOS tournant en
parallèle. Rien de la chaîne n'en dépend ; `hdiutil detach -force` a suffi. C'est écrit ici
pour qu'un code de sortie non nul sur cette étape ne fasse pas recommencer deux envois.

### Ce qui reste, et qui n'est pas à moi

Les deux mêmes gestes que pour la 1.8.1 — la publication qui sert l'image, et l'entrée
d'appcast signée — et ils attendent l'accord de Clara, parce que signer l'entrée pousse le
binaire à tout le parc. Voir « Une publication restée en brouillon ne sert rien » plus haut :
c'est précisément ce couple qui s'est désaccordé le même jour.

## La notarisation du 2026-11-03

`GhostCal 1.8.1 (13)`, depuis `86b89c6`, soit `main` sans rien de plus. Faite parce qu'un
client a signalé deux choses qui n'étaient pas des défauts : il ne pouvait pas supprimer un
calendrier, et ne voyait pas ses abonnements. Les deux gestes sont arrivés dans la 1.8.0,
les 24 et 27 octobre. La dernière image servie est la **1.6.0**, du 23 octobre : elle est
antérieure aux deux, donc aucun retéléchargement ne pouvait les lui donner — il en a fait
un, sans rien y gagner.

Ce diagnostic a d'abord été rendu faux par ce document : son tableau s'arrêtait à la 1.4.1,
donc la 1.4.1 a été annoncée à Clara comme la version du client. Le flux Sparkle et la page
de téléchargement disaient tous deux 1.6.0. **Ce que sert le site se lit sur le site**, pas
dans le dépôt.

| | |
|---|---|
| Envoi de l'application | `d5cf2637-7fac-4d42-8a00-ee23d27823a2` — **Accepted** |
| Envoi de l'image refabriquée autour de l'application agrafée | `be799f1a-c140-4b4d-8e91-b18bdd7f205e` — **Accepted** |
| `spctl -t install` sur l'image | `accepted`, `source=Notarized Developer ID` |
| `spctl -t exec` sur l'application montée | `accepted`, `source=Notarized Developer ID` |
| `stapler validate` | passe sur l'image **et** sur l'application |
| `get-task-allow` | absent |
| Horodatage de l'image | `3 Nov 2026 at 21:10:43` |

### Ce qui reste, et sans quoi personne ne la reçoit

**La notarisation ne distribue rien.** Deux gestes manquent, et ils ne touchent pas le même
monde :

1. **Servir l'image** — publication de la forge sur `mobile-v1.8.1` (l'étiquette n'existe
   pas encore : les étiquettes s'arrêtent à `mobile-v1.8.0`), et le site qui l'annonce avec
   son numéro de version et sa somme.
2. **L'entrée d'appcast**, signée avec la clé Sparkle — moitié privée dans le Bao sous
   `kv/ghostcal/sparkle`, et dans le trousseau de cette machine sous le compte `ghostcal`.
   Sans elle, `https://ghostsuite.cloud/ghostcal/appcast.xml` continue d'annoncer
   l'ancienne, et le parc ne bouge pas.

**Et lui n'aura rien à faire**, une fois l'entrée posée. Sparkle est arrivé dans la 1.6.0
(`48d3192`), qui est précisément ce que sert le site : sa copie interroge le flux une fois
par jour et lui proposera la 1.8.1 d'elle-même. Inutile de lui demander de retélécharger —
il l'a déjà fait une fois pour rien, parce que la page lui a resservi la même version.

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
| Une série récurrente survit à une modification depuis le Mac | `tools/semer-une-serie.py` dépose une série dont le rappel est posé **par le serveur**, comme le web le fait. Le témoin modifie la série depuis l'application, retire une occurrence, puis supprime tout — et relit `rrule`, `exdates` et `reminder_minutes` **sur le serveur** à chaque étape. Un titre correct à l'écran ne dit rien de ce qui a été écrit, et c'est là que la perte se produisait : la route `PUT` remplace l'enregistrement entier |
| Les deux côtés parlent la même langue | `test/menu_macos_test.dart` compare les noms de méthode émis par le Swift à ceux traités par `accueil.dart`, dans les deux sens. Sans témoin, un item renommé d'un seul côté donne un raccourci qui ne fait rien, en silence |

### Ce que les témoins ne peuvent pas atteindre, et ce que ça coûte

**`EcranDAccueil` ne se monte pas en test.** Pas « mal » : pas du tout. Un `pumpWidget`
avec une `Session()` nue lève à la construction — il lui faut une session ouverte, donc un
serveur et le cœur Rust. C'est pourquoi `test/menu_macos_test.dart` et `test/fond_test.dart`
lisent le **source** au lieu de monter quoi que ce soit, et ils le disent tous les deux
dans leur en-tête.

La conséquence est précise : chaque morceau de l'accueil s'éprouve **seul** —
`BarreDeTitreDeBureau`, `ColonneLaterale`, les boîtes de dialogue —, et le **chaînage**
n'est gardé par rien. Un composant juste, branché nulle part, passe au vert.

Ce n'est pas une inquiétude de principe, c'est arrivé deux fois en deux jours :

| Le défaut | Pourquoi aucun témoin n'a mordu |
|---|---|
| La barre d'outils posée sur l'heure de l'iPad | `Mesures.dansLaBarreDeTitre` **préservait** la marge haute, et `_barreDeTitre` ne la lisait pas. Deux témoins purs au vert au-dessus : une fonction pure reste verte quand le défaut est de ne **pas** l'appeler |
| Les abonnements ICS invisibles | Le filtre des calendriers est une liste de **masqués** et non d'autorisés, donc les événements d'un flux passaient — sans nom, sans couleur propre, sans case. Un écran cohérent et faux, et rien pour le signaler |

Les deux ont la même forme : **la chose était là, personne ne la lisait.** C'est exactement
ce qu'un témoin de composant ne voit pas.

Ce qui manquerait pour le garder : des bouchons de session permettant de monter l'accueil.
C'est une dette consignée et non un chantier en cours — la bricoler dans la précipitation
donnerait un harnais qu'on croit, ce qui est le pire des deux états.

En attendant, deux habitudes tiennent lieu de filet, et elles ont trouvé des défauts que
les témoins avaient laissés passer :

- **remettre le défaut.** Un témoin qu'on n'a pas vu échouer ne dit rien. Les mutations qui
  **passent** valent autant que celles qui échouent : elles disent où il ne protège pas.
- **regarder l'écran, pas seulement la mesure.** Un témoin qui ne relève aucun débordement
  et une capture qu'on ouvre ne disent pas la même chose. La barre posée sur l'heure a été
  vue en image, après deux témoins verts.

### Trois façons de croire qu'on a vérifié

Les trois sont arrivées sur ce dépôt en une semaine, à deux sessions différentes. Elles ont
la même forme : non pas l'absence de vérification, mais **sa sensation sans sa substance**.

**Un témoin rouge qui devient vert ressemble trop à une preuve.** La vue Année marquait
« aujourd'hui » dans les deux grilles qui le contiennent. Le témoin était rouge, une
condition l'a fait repasser au vert, et ça a été présenté comme une démonstration. Mais ce
témoin lisait `DateTime.now()` comme la vue qu'il éprouvait : il ne mesurait que **le jour
où il tournait**, et il serait reparti au vert le lendemain, défaut remis ou pas. Un témoin
jamais vu échouer se soupçonne ; celui-là **s'était manifesté sous la main**, et c'est ce
qui éteint le soupçon. D'où l'horloge injectable et des dates choisies — voir
`test/agenda_annee_test.dart`.

**Un état vérifié est vrai à une date — y compris quand c'est soi qui l'a vérifié.** La
règle existait déjà pour les relevés d'autrui, après qu'une fiche a affirmé pendant deux
jours « aucun accès Play Console » là où le chemin existait et avait servi. Elle lui
manquait un cran : une branche lue le 24, corrigée le 25, a été rapportée dans l'état du 24
le 27 — par celui-là même qui venait de l'avoir lue. Sa propre lecture est un relevé comme
un autre.

**Une explication qui met hors de cause se vérifie moins qu'une autre, pas plus.** Les deux
sessions l'ont fait dans la même minute, sur la même question, en se reprochant l'inverse :
l'une a avancé « la PR est épinglée à un vieux commit » et l'autre l'a relayée, sans que
personne regarde. La cause était plus simple et moins flatteuse — personne n'avait relu. Et
la suivante aussi : un auteur de commit inattendu a fait conclure à une machine mal
identifiée, alors qu'un champ avait simplement été **écrit à la main** dans un appel d'API.
Une métadonnée qu'on peut écrire ne dit pas qui a agi ; elle dit ce que l'appelant y a mis.

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
