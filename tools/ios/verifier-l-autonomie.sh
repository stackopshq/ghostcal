#!/usr/bin/env bash
# Vérifie que l'application GhostCal livrée ne vend rien et ne dépend de personne.
#
#   ./tools/ios/verifier-l-autonomie.sh [chemin/vers/Runner.app]
#
# Sans argument, il prend le paquet Release de `flutter build ios`.
#
# ─── Pourquoi ce contrôle existe ───
#
# GhostCal est **gratuit**. Ce qui se paie, chez ceux qui ne veulent pas auto-héberger,
# est la mise à disposition d'une machine — pas le logiciel. C'est une qualification
# juridique, et le relecteur d'Apple ne juge pas sur la qualification : il juge sur ce que
# **contient l'application**. Une mention d'abonnement dans le binaire suffit à faire
# relire la soumission au titre de la règle 3.1.1 sur les achats intégrés.
#
# ─── Pourquoi on scanne le binaire et pas les sources ───
#
# La fiche App Store parle légitimement de tarif, les ADR d'abonnement, et ce fichier-ci
# écrit les mots qu'il interdit. Un grep sur le dépôt exigerait une liste d'exclusions qui
# pourrit, et finirait par se scanner lui-même. Le relecteur, lui, ne lit pas le dépôt :
# il lit le paquet. C'est donc le paquet qu'on mesure.
#
# ─── Les trois instruments qui ont menti, le 25 septembre 2026 ───
#
# Ce script est passé par trois versions fausses avant celle-ci, et chacune était verte
# ou rouge pour une mauvaise raison. Elles valent d'être écrites, parce qu'elles disent ce
# qu'on ne peut pas croire sur parole.
#
# 1. `strings` ne rend que de l'ASCII imprimable. Une chaîne UTF-8 accentuée y est
#    **coupée à chaque accent** : « Réunions » devient « R » puis « unions ». Mesuré sur
#    ce paquet — `strings -a … | grep -c Réunions` rend **0**, alors que la chaîne y est.
#    `strings -a -e S` rend 0 lui aussi. Le vocabulaire cherché ici contient « abonné »,
#    « achat intégré », « payé » : avec `strings`, ces mots-là n'auraient **jamais** pu
#    rougir. Le contrôle serait resté vert en ne regardant rien.
#
# 2. `grep -a` voit les accents, mais lit le binaire **octet par octet**. Le motif de prix
#    `[€£][0-9]` devient alors un jeu d'octets : `€` s'écrit E2 82 AC en UTF-8, et
#    n'importe lequel de ces trois octets suivi d'un chiffre déclenchait une
#    correspondance. Le contrôle rougissait sur cinq fichiers, dont `NOTICES.Z` — du
#    texte de licence compressé, où aucun prix ne figure.
#
# 3. `sort` et `sed` s'étranglent sur les octets qui ne forment aucun caractère valide
#    (« Illegal byte sequence ») : ils tronquent leur sortie **sur stdout** tout en se
#    plaignant sur stderr. Le contrôle rendait moins de correspondances qu'il n'en avait
#    trouvé, sans que cela se voie.
#
# D'où le cœur de ce script : un `strings` conscient de l'UTF-8, écrit en Python. Il
# extrait les suites de caractères **imprimables** du binaire — accents compris, octets
# invalides exclus — puis cherche dans ces chaînes-là. Les trois pièges tombent ensemble.
#
# ─── Où vivent les chaînes dans un paquet Flutter ───
#
# Pas dans le binaire principal. `Runner` n'est qu'un hôte : le code Dart compilé vit dans
# `Frameworks/App.framework/App`, l'instantané AOT. Mesuré : « Agenda » rend 6 occurrences
# dans `App.framework/App` et **0** dans `Runner`. Un contrôle qui n'examinerait que le
# binaire principal serait vert sur une application couverte de vitrines.
#
# ─── Ce que ce script ne prouve pas ───
#
# L'absence de vitrine n'est pas l'autonomie. Ce qui prouve qu'on fonctionne sans StackOps,
# c'est un parcours de premier lancement aboutissant à un agenda utilisable contre une
# instance quelconque. Si ce parcours disparaît, ce script reste vert et ne veut plus rien
# dire.
#
# Et il ne dit rien de l'état des directives d'Apple, qui ont bougé plusieurs fois. Elles
# sont à relire sur le texte en vigueur avant chaque soumission.
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP="${1:-$RACINE/apps/mobile/build/ios/iphoneos/Runner.app}"

if [[ ! -d "$APP" ]]; then
  echo "Aucun paquet .app à examiner : $APP" >&2
  echo "Construisez d'abord — (cd apps/mobile && flutter build ios --release --no-codesign)" >&2
  exit 2
fi

export APP RACINE
python3 - <<'PYTHON'
import os, re, sys

APP = os.environ["APP"]
RACINE = os.environ["RACINE"]

VERT, ROUGE, JAUNE, GRAS, FIN = "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[0m"

# ─── Ce qu'on n'examine pas, et pourquoi ───
#
# `Flutter.framework` est le moteur de Google : du code tiers, livré tel quel, que ce
# dépôt ne peut pas corriger. Il porte le vocabulaire des plateformes — `upgrade`,
# `purchase` apparaissent dans des symboles de Skia et de Dart — et l'y chercher ferait
# rougir le contrôle sur du code qui n'est pas le produit.
#
# C'est le piège qu'a connu GhostPass avec les frameworks de test d'Apple : son contrôle
# accusait l'application livrée pour un `upgradeCapability:` appartenant à `XCTestSupport`.
# Et le même sur Android, où `SubscriptionCountStateFlow` vient de la plateforme.
#
# Les bundles des greffons sont exclus pour la même raison : leur texte n'est pas le nôtre.
#
# Ce qui reste — `Runner`, `App.framework/App`, le cœur Rust, les ressources du produit —
# est exactement ce que nous écrivons ou assemblons.
EXCLUS_CHEMIN = (
    "/_CodeSignature/",
    "/Frameworks/Flutter.framework/",
    "local_auth_darwin",
    "flutter_secure_storage_darwin",
    "flutter_timezone",
)
EXCLUS_SUFFIXE = (".png", ".jpg", ".car")


def fichiers_du_produit():
    for dossier, _, noms in os.walk(APP):
        for nom in noms:
            chemin = os.path.join(dossier, nom)
            rel = chemin[len(APP) + 1:]
            if any(m in chemin for m in EXCLUS_CHEMIN):
                continue
            if nom.lower().endswith(EXCLUS_SUFFIXE):
                continue
            yield chemin, rel


# ─── Le `strings` qui sait lire les accents, et les deux encodages ───
#
# **Le point le plus contre-intuitif de ce fichier**, mesuré le 25 septembre 2026.
#
# Dart stocke une chaîne dont tous les caractères tiennent sur un octet en **Latin-1**,
# un octet par caractère (`OneByteString`). Dans l'instantané AOT, « Disponibilités »
# s'écrit donc `Disponibilit\xe9s` — et **pas** `Disponibilit\xc3\xa9s`, sa forme UTF-8.
# Vérifié : l'octet UTF-8 est introuvable dans le binaire, le Latin-1 est à l'offset
# 6 264 880. Idem pour « Réunions » et « Tâches ».
#
# Et `grep -ac 'Disponibilités'` rend pourtant **1** sur ce fichier. Il ment : la suite
# d'octets qu'on lui a donnée n'y est pas. C'est le quatrième instrument à mentir dans
# cette enquête, après `strings`, `sort` et `sed`.
#
# Conséquence : un contrôle qui ne décoderait qu'en UTF-8 ne verrait **aucun** mot
# accentué de l'application. « abonné », « payante », « achat intégré » : tous invisibles.
# Il serait vert, et ne regarderait rien.
#
# Et il y a un **troisième** encodage, découvert en éprouvant ce script par mutation.
# Dès qu'une chaîne Dart contient un seul caractère au-delà de U+00FF, elle bascule en
# `TwoByteString` : UTF-16, deux octets par caractère. Le tiret cadratin « — », le
# demi-cadratin « – » et l'apostrophe typographique « ’ » suffisent — et ce dépôt en est
# plein. Mesuré : **19 littéraux** de `lib/` en contiennent, dont « Contenu illisible —
# clé manquante » et « Elle sera effacée à l’enregistrement. ».
#
# La mutation qui l'a révélé : « Version payante — la facturation reprendra en février »
# injectée dans un écran, reconstruite, et **non détectée**. Le contrôle était vert sur
# une vitrine qu'il avait sous les yeux. Sans cette épreuve, la faille serait passée.
#
# On extrait donc trois fois, et on réunit :
#
#   · en **Latin-1** — l'encodage des chaînes Dart sans caractère exotique.
#   · en **UTF-16LE** — celui des chaînes Dart qui en portent un.
#   · en **UTF-8**   — celui des fichiers qui en sont vraiment, Info.plist et NOTICES.
#
# Un fichier UTF-8 lu en Latin-1 donne du charabia (« Ã© ») dont les parties ASCII
# restent justes ; un fichier Latin-1 lu en UTF-8 perd ses accents. Chaque passe rattrape
# ce que les autres laissent tomber, et la réunion ne peut que voir plus.

# Imprimable en Latin-1 : l'ASCII imprimable, plus la plage des lettres accentuées.
# `\x80-\x9f` en est exclu : ce sont des commandes, pas des lettres.
IMPRIMABLE_LATIN1 = re.compile(r"[^\x20-\x7e\xa0-\xff]")
IMPRIMABLE_UTF8 = re.compile(r"[^\S ]|[\x00-\x1f\x7f\ufffd]")


def _decouper(texte, separateur, minimum):
    for morceau in separateur.split(texte):
        morceau = morceau.strip()
        if len(morceau) >= minimum:
            yield morceau


def chaines(chemin, minimum=4):
    """Les suites de caractères imprimables du fichier, dans les deux encodages.

    Rend `None` — et non une liste vide — quand le fichier n'a pas pu être lu. « Je n'ai
    pas pu regarder » n'est pas « je n'ai rien trouvé », et l'appelant doit pouvoir faire
    la différence.
    """
    try:
        with open(chemin, "rb") as f:
            brut = f.read()
    except OSError:
        return None
    trouvees = set()
    trouvees.update(_decouper(brut.decode("latin-1"), IMPRIMABLE_LATIN1, minimum))
    trouvees.update(
        _decouper(brut.decode("utf-8", errors="replace"), IMPRIMABLE_UTF8, minimum)
    )
    # Les deux alignements : rien ne garantit qu'une chaîne UTF-16 commence à un offset
    # pair dans le fichier. N'en lire qu'un rendrait la détection dépendante du hasard
    # de la mise en page du binaire — verte un jour, rouge le lendemain, sans qu'on
    # touche à rien.
    for depart in (0, 1):
        morceau = brut[depart:]
        if len(morceau) % 2:
            morceau = morceau[:-1]
        trouvees.update(
            _decouper(morceau.decode("utf-16-le", errors="replace"), IMPRIMABLE_UTF8, minimum)
        )
    return trouvees


# ── Contrôle 1 : le vocabulaire qui ne peut pas venir d'un moteur ──
#
# Du français, et des locutions anglaises de plusieurs mots. Ni le SDK Dart, ni le moteur
# Flutter, ni CocoaPods n'écrivent « essai gratuit » ou « in-app purchase ». Une
# correspondance ici est une vitrine, sans discussion possible.
VITRINE_CERTAINE = re.compile(
    r"abonnement|s['’]abonner|abonnez|abonné|tarif|forfait|payante?\b|facturation"
    r"|paiement|acheter|achat intégré|essai gratuit|passer .{1,14} version"
    r"|free trial|in-app purchase|restore purchase|start your trial|subscribe now"
    r"|upgrade to|premium plan|paid plan",
    re.IGNORECASE,
)

# ── Contrôle 2 : les mots ambigus, et seulement en prose ──
#
# « subscription », « upgrade », « premium », « purchase », « checkout » peuvent être des
# identifiants — et le sont, ici. Mesuré sur ce paquet : `StreamSubscription`,
# `_socketSubscription`, `_BufferingStreamSubscription@5048458`, un getter `upgrade`.
# Aucun ne vient de nous : `grep -rniE` sur `lib/`, hors bindings générés, rend **zéro**
# occurrence de ces mots dans notre code.
#
# Et on ne peut pas les écarter par fichier comme on écarte un framework : notre code Dart
# et la bibliothèque standard de Dart sont compilés dans **le même** instantané AOT. Il
# n'y a pas de fichier à retirer.
#
# Ce qui les sépare n'est pas leur emplacement, c'est leur nature : une vitrine est une
# **phrase adressée à un humain**, un `StreamSubscription` est un identifiant. On exige
# donc que la chaîne entière ressemble à de la prose — au moins trois mots, et pas de
# `@`, `_`, `:` ou `$` qui trahissent un symbole.
AMBIGU = re.compile(r"\b(subscription|upgrade|premium|purchase|checkout)\b", re.IGNORECASE)
SYMBOLE = re.compile(r"[@_$:()\[\]<>]|\d{4,}")

# Les phrases du SDK qui passent malgré tout cette épreuve, relevées le 25 septembre 2026.
# Chaque entrée est une **chaîne entière**, comparée à l'identique : une tolérance
# nommée se relit, une liste d'exclusions par fichier pourrit. Une tolérance qui
# accepterait « … upgrade to premium » serait une porte ouverte, pas une exception.
TOLEREES = {
    "Subscription passed to TLS upgrade is paused",
}


def est_de_la_prose(chaine):
    if SYMBOLE.search(chaine):
        return False
    mots = [m for m in chaine.split() if len(m) >= 3]
    return len(mots) >= 3


# ── Contrôle 3 : un prix affiché ──
#
# Deux pièges se sont refermés ici, l'un après l'autre.
#
# Le premier : le code de devise sans limites de mot. `erreur33` contient « eur3 », et le
# contrôle rougissait sur toute l'application — mesuré chez GhostPass, pas supposé. D'où
# les `\b` et la sensibilité à la casse.
#
# Le second, propre à la lecture Latin-1 introduite plus haut : l'octet `0xA3` s'y décode
# en `£`. Un binaire en contient par milliers, et `[€£][0-9]` a fait rougir cinq fichiers
# sur des suites comme « @ù£1 » ou « %ã£4 ». Du bruit, présenté comme un prix affiché.
#
# On n'applique donc ce contrôle qu'aux chaînes qui sont **du texte lisible**. Un prix en
# vitrine vit dans une phrase ; un `£` de bruit vit entre deux octets sans lettres.
PRIX = re.compile(
    r"\b(CHF|EUR|USD)\b\s*[0-9]|[0-9]\s*\b(CHF|EUR|USD)\b|[€£]\s?[0-9]|\$[0-9]+[.,][0-9]{2}"
)

MOT_ASCII = re.compile(r"[A-Za-z]{3,}")


def est_lisible(chaine):
    """Cette chaîne ressemble-t-elle à du texte écrit pour un humain ?

    Deux conditions, chacune contre un bruit observé, et la seconde n'est pas celle qu'on
    écrit d'instinct.

    · **Un mot ASCII d'au moins trois lettres.** Du bruit Latin-1 en contient parfois ;
      ce seul critère ne suffit pas, il a laissé passer « z¨bÐÍvHìÒ£1ÞHrñxÓjav- ».

    · **Au moins 85 % de caractères ASCII.** C'est celui qui tranche. Le bruit d'un
      binaire lu en Latin-1 est saturé d'octets hauts — « cÜFù£6 » plafonne à 50 %.
      Un texte français, lui, est de l'ASCII avec quelques accents : « 9,90 € par mois »
      atteint 93 %, « CHF 9.90 par mois » 100 %.

    Le premier jet mesurait « au plus un cinquième de caractères hors alphabet », en
    s'appuyant sur `str.isalnum()`. Il ne filtrait rien : `isalnum()` est conscient de
    l'Unicode, et tient `Ü`, `ù`, `Í` pour des lettres — ce qu'elles sont. Le bruit
    Latin-1 est donc, à ses yeux, presque entièrement alphabétique.
    """
    if not MOT_ASCII.search(chaine):
        return False
    ascii_ = sum(1 for c in chaine if ord(c) < 128)
    return ascii_ >= 0.85 * len(chaine)


# ── Contrôle 4 : une dépendance à l'infrastructure de l'éditeur ──
#
# L'application doit marcher contre n'importe quelle instance ; un point de terminaison en
# dur dirait le contraire.
EDITEUR = re.compile(r"stackops\.ch|ghostsuite\.cloud", re.IGNORECASE)


# ─── Épreuve de l'instrument, avant de croire quatre verts ───
#
# On cherche une chaîne **accentuée** que l'application contient à coup sûr. Si elle ne se
# trouve pas, ce n'est pas que l'application a changé : c'est que la lecture ne voit plus
# le contenu, et les quatre contrôles seraient verts sans rien lire. C'est précisément la
# panne qu'avait `strings`.
TEMOIN = "Disponibilités"

# ─── Le relevé ───

corpus = []      # (rel, chaîne)
illisibles = []  # fichiers qu'on n'a pas pu ouvrir : ni vert ni rouge
examines = 0

for chemin, rel in fichiers_du_produit():
    extrait = chaines(chemin)
    if extrait is None:
        illisibles.append(rel)
        continue
    examines += 1
    for c in extrait:
        corpus.append((rel, c))

print(f"Paquet examiné : {APP[len(RACINE) + 1:]}")
print(f"{examines} fichiers, {len(corpus)} chaînes extraites")
print()

fautes = 0

if illisibles:
    print(f"{JAUNE}· {len(illisibles)} fichier(s) illisible(s) — le contrôle n'a pas pu les regarder{FIN}")
    for rel in illisibles[:5]:
        print(f"    {rel}")
    fautes += 1

if examines == 0:
    print(f"{JAUNE}· AUCUN FICHIER EXAMINÉ — le contrôle n'a rien pu regarder.{FIN}")
    print("  Un paquet vide ou réorganisé rendrait autrement ce script vert et muet.")
    sys.exit(2)

if not any(TEMOIN in c for _, c in corpus):
    print(f"{JAUNE}· témoin « {TEMOIN} » introuvable — la méthode de lecture ne voit rien.{FIN}")
    print("  Les contrôles qui suivent seraient verts sans avoir rien lu. On s'arrête.")
    print("  (Paquet Debug au lieu de Release ? Libellé de l'écran Réglages renommé ?)")
    sys.exit(2)
print(f"{VERT}✓ témoin de lecture — « {TEMOIN} » retrouvé dans le paquet{FIN}")
print()


def controler(nom, predicat):
    global fautes
    trouve = {}
    for rel, chaine in corpus:
        if predicat(chaine):
            trouve.setdefault(rel, set()).add(chaine)
    if trouve:
        print(f"{ROUGE}✗ {nom}{FIN}")
        for rel, ensemble in sorted(trouve.items()):
            print(f"  {rel} :")
            for c in sorted(ensemble)[:5]:
                print(f"    {c[:110]}")
        print()
        fautes += 1
    else:
        print(f"{VERT}✓ {nom}{FIN}")


controler(
    "aucune vitrine — vocabulaire sans ambiguïté",
    lambda c: bool(VITRINE_CERTAINE.search(c)),
)
controler(
    "aucun mot de vitrine employé en prose",
    lambda c: bool(AMBIGU.search(c)) and est_de_la_prose(c) and c not in TOLEREES,
)
controler("aucun prix affiché", lambda c: est_lisible(c) and bool(PRIX.search(c)))
controler(
    "aucun point de terminaison de l'éditeur en dur",
    lambda c: bool(EDITEUR.search(c)),
)

print()
print("Rappel : ce script ne mesure que l'absence de vitrine. L'autonomie réelle se prouve")
print("par un premier lancement qui aboutit à un agenda utilisable contre une instance")
print("quelconque — l'adresse du serveur se saisit à l'écran de connexion.")

if fautes:
    print()
    print("L'application soumise contiendrait de quoi la faire relire au titre des achats")
    print("intégrés. Retirez ces chaînes du paquet, ou assumez la soumission en le sachant.")
    sys.exit(1)
PYTHON
