# Fiche App Store — GhostCal

Textes prêts à coller dans App Store Connect. **Rien ici n'est une promesse commerciale
que le code ne tiendrait pas** : chaque affirmation a été vérifiée dans `apps/mobile/lib/`
le 25 septembre 2026, écran par écran.

> Les mentions entre crochets restent à trancher : elles engagent l'entreprise, pas le
> dépôt. Elles sont rassemblées en fin de document.

**Cette fiche décrit le projet Flutter**, `apps/mobile/ios/Runner.xcodeproj`, identifiant
`ch.stackops.ghostcal`. Il existe un second projet iOS dans ce dépôt,
`apps/ios/Ghostcal.xcodeproj`, écrit en SwiftUI et **remplacé** par celui-ci. Il ne part
pas chez Apple.

## Ce qui manque avant l'envoi

Relevé le 25 septembre 2026.

| Ce qu'il reste | Pourquoi ça ne peut pas se faire ici |
|---|---|
| **Un jeu de captures livrable** | L'outillage marche et produit des images à la bonne taille ; le banc qu'il photographie est un banc d'épreuve, pas une vitrine. Voir « Captures d'écran » |
| **Le compte de démonstration** pour l'examinateur | Il doit vivre sur une instance joignable de l'extérieur |
| **L'instance publique** à indiquer dans les notes | Question d'exploitation |
| Les **URL** de confidentialité et d'assistance | Aucune page GhostCal en ligne au 25/09 — voir « URL » |
| Trancher la **note 3 du §740.17(b)** et mener les démarches BIS et ANSSI | Questions de droit ; GhostPass a le même arbitrage en cours |
| Coller la fiche et répondre au questionnaire de confidentialité | Les réponses exactes sont plus bas, mot pour mot |
| Envoyer l'archive | `tools/ios/archiver-appstore.sh` la construit et la mesure ; l'envoi reste une décision |

Ce qui est prêt : `ExportOptions.plist`, le manifeste de confidentialité (câblé dans la
cible et **mesuré dans le paquet construit**), l'outillage d'archive avec ses contrôles,
le contrôle d'autonomie éprouvé par mutation, les icônes, et les textes ci-dessous.

## Identité

| Champ | Valeur |
|---|---|
| Nom | GhostCal |
| Sous-titre (30 car. max) | **[à trancher]** — propositions ci-dessous |
| Catégorie principale | **[à trancher]** — Productivité ou Entreprise |
| Catégorie secondaire | Utilitaires |
| Classification d'âge | **[à trancher]** — 4+ *a priori* |
| Appareils | iPhone **et** iPad (`TARGETED_DEVICE_FAMILY = "1,2"`, relevé dans le projet) |
| Prix | **Gratuit** |

**Sous-titre — trois propositions, aucune tranchée.** Chacune est vraie du produit livré :

| Proposition | Caractères | Ce qu'elle met en avant |
|---|---|---|
| Votre agenda, sur votre serveur | 31 — **trop long d'un** | L'auto-hébergement |
| Agenda chiffré, auto-hébergé | 28 | Les deux arguments |
| Vos rendez-vous, chiffrés | 25 | Le chiffrement |
| Votre agenda sur votre serveur | 30 | L'auto-hébergement, sans virgule |

**Catégorie — pourquoi ce n'est pas évident.** GhostPass est en « Utilitaires », ce qui
convient à un coffre. GhostCal fait de la prise de rendez-vous et de la gestion d'équipe :
« Productivité » est plus juste, et c'est là que vivent les produits comparables.
« Entreprise » réduirait fortement la visibilité. Je propose **Productivité** en
principale et **Utilitaires** en secondaire, mais c'est un choix de positionnement.

**Classification d'âge.** L'application ne contient aucun contenu généré par des tiers et
n'ouvre aucun navigateur. Elle affiche en revanche des **liens de visioconférence** saisis
par l'utilisateur, et le questionnaire d'Apple demande si l'app donne accès à du contenu
web non filtré. Le code ne les ouvre pas — il les affiche en texte (`reunions.dart`) — ce
qui plaide pour **4+**. À confirmer en remplissant le formulaire, qui pose la question
autrement chaque année.

## Description (français)

> Relue contre le code le 25 septembre 2026. Chaque paragraphe renvoie à un écran qui
> existe et à une action qui marche.

GhostCal est un agenda et un outil de prise de rendez-vous que vous hébergez vous-même.

Le titre, le lieu et la description de vos événements sont chiffrés sur votre appareil,
avec une clé dérivée de votre phrase de passe. Cette phrase ne quitte jamais l'appareil.
Le serveur conserve les horaires — il lui faut bien savoir quand vous êtes occupé pour
refuser une réservation qui se chevauche, et pour envoyer les rappels — mais il ne sait
pas de quoi il s'agit.

VOTRE JOURNÉE
L'agenda du jour, vos calendriers, et les événements que vous créez depuis l'application :
titre, lieu, description, horaires, journée entière.

VOS TÂCHES
Avec leur échéance, triées par urgence. Leur titre et leurs notes sont chiffrés eux aussi.

VOS RENDEZ-VOUS RÉSERVÉS
Les réunions prises par vos invités depuis vos liens publics : qui, quand, où, et leurs
réponses à vos questions. Vous pouvez en annuler une depuis l'application.

VOS LIENS DE RÉSERVATION
Activez ou désactivez un type de rendez-vous, et copiez son lien public d'un geste pour
l'envoyer.

VOS SONDAGES DE CRÉNEAUX
Voyez qui a voté pour quoi, et retenez le créneau qui l'emporte.

VOTRE ÉQUIPE
Les membres de votre organisation, leurs rôles, et de quoi les changer.

FACE ID
Face ID ou Touch ID rouvrent votre agenda sans ressaisir la phrase. Elle est scellée par
le matériel de l'appareil : ajouter un visage ou une empreinte invalide le sceau, et
GhostCal vous le dit au lieu de faire semblant. Le verrouillage automatique se règle —
immédiatement, ou après 1, 5 ou 15 minutes.

SUR VOTRE SERVEUR
Vous saisissez l'adresse de votre instance au premier écran. GhostCal ne connaît aucun
serveur par défaut et n'en impose aucun.

Aucun traceur. Aucune publicité. Aucune analyse comportementale.

## Description (anglais)

GhostCal is a calendar and scheduling tool that you host yourself.

The title, location and description of your events are encrypted on your device, with a
key derived from your passphrase. That passphrase never leaves the device. The server
keeps the times — it has to know when you are busy in order to turn down an overlapping
booking, and to send reminders — but it does not know what any of it is about.

YOUR DAY
The day's agenda, your calendars, and the events you create from the app: title, location,
description, times, all-day.

YOUR TASKS
With their due dates, sorted by urgency. Their titles and notes are encrypted too.

YOUR BOOKED MEETINGS
The meetings your invitees took through your public links: who, when, where, and their
answers to your questions. You can cancel one from the app.

YOUR BOOKING LINKS
Turn an event type on or off, and copy its public link in one tap to send it.

YOUR TIME POLLS
See who voted for what, and pick the slot that wins.

YOUR TEAM
The members of your organisation, their roles, and what it takes to change them.

FACE ID
Face ID or Touch ID reopen your calendar without retyping the passphrase. It is sealed by
the device's hardware: adding a face or a fingerprint invalidates the seal, and GhostCal
tells you so instead of pretending. Auto-lock is configurable — immediately, or after 1,
5 or 15 minutes.

ON YOUR SERVER
You enter your instance's address on the first screen. GhostCal knows no default server
and imposes none.

No trackers. No ads. No behavioural analytics.

## Ce que la description ne dit pas, délibérément

Cette liste est la contrepartie de la précédente. Chaque ligne est une fonctionnalité que
les concurrents annoncent, que GhostCal **n'a pas** dans son application iOS, et qu'il
serait tentant d'écrire.

| Absent | Vérifié |
|---|---|
| **Tout est chiffré** | Faux. Horaires, fuseaux, adresses e-mail, noms de calendriers, titres de réunions et lieux partent en clair. Seuls le titre/lieu/description d'un événement et le titre/notes d'une tâche sont scellés. L'application le dit elle-même à l'écran de création |
| **Accès hors ligne** | Aucun cache, aucune base locale, aucune file de synchronisation. Sans réseau, rien ne s'affiche |
| **Rappels, notifications** | Aucune dépendance de notification, aucun code. Les rappels partent **du serveur, par courriel** |
| **Invitation de participants à un événement** | L'écran de création n'a pas ce champ |
| **Événements récurrents** | Non créables ; les occurrences d'une série existante sont affichées mais **non modifiables** |
| **Vue semaine ou mois** | L'agenda est en **jour unique** |
| **Création de sondages, de types de rendez-vous, d'horaires** | Consultation et bascule seulement. L'app écrit elle-même « Ils se créent depuis le web » |
| **Invitation d'un membre dans l'équipe** | Aucun bouton d'invitation |
| **Changement de mot de passe ou de phrase** | La fonction Rust qui le ferait (`chiffrerSymetrique`) n'est appelée nulle part dans `lib/` |
| **Photo de profil** | On peut la retirer, jamais l'ajouter. Aucun sélecteur d'image |
| **Import / export** | Aucun |
| **Application en anglais** | Les textes sont en dur en français. Seuls les composants fournis par Flutter sont traduits, et uniquement en français. Ne déclarer que « Français » dans App Store Connect |

**Un point à assumer plutôt qu'à découvrir en revue :** plusieurs fonctions renvoient
explicitement au web. C'est cohérent et l'application le dit poliment, mais un examinateur
peut y voir une app « incomplète » au titre de la règle 4.2 sur le contenu minimal. Les
notes d'examen doivent donc mettre en avant ce que l'app fait **seule** : créer et
modifier des événements, gérer des tâches, annuler des réunions, basculer des liens de
réservation, arbitrer des sondages, administrer les rôles d'équipe. C'est un usage entier,
pas une télécommande.

## Mots-clés (100 caractères, virgules comprises)

```
agenda,rendez-vous,chiffré,calendrier,réservation,planning,vie privée,équipe,réunion
```

83 caractères. Le nom de l'app et les catégories sont déjà indexés : les répéter ici
gaspillerait la limite. Les marques concurrentes n'y figurent pas — Apple les refuse.

**Ce qui a été retiré, et pourquoi.** « hors ligne » : l'application n'a aucun mode hors
ligne. « notifications » et « rappels » : ils viennent du serveur par courriel, pas de
l'app. « synchronisation » : il n'y a ni cache ni fusion, seulement des appels réseau.
Un mot-clé qui promet une fonctionnalité absente se paie à la revue, et déçoit celui qui
installe pour ça.

## Nouveautés de cette version

```
Première version.
```

## URL

| Champ | Valeur proposée | État au 25/09/2026 |
|---|---|---|
| Politique de confidentialité | **[à créer]** | **rien en ligne** |
| Assistance | **[à créer]** | **rien en ligne** |
| Marketing | `https://ghostsuite.cloud/` | en ligne, facultatif |

Les deux premières sont **obligatoires** chez Apple, et **c'est le point bloquant le plus
certain de cette fiche**. GhostPass a pu lier `https://ghostsuite.cloud/confidentialite/`,
qui couvre les produits nommément ; il faut vérifier que **GhostCal y est nommé**, et non
supposer que la page suffit parce qu'elle existe.

Le dépôt n'a **pas** de brouillon de politique de confidentialité pour GhostCal — GhostPass
a `docs/confidentialite.md`, GhostCal n'a pas d'équivalent. Et le texte ne peut pas être
recopié : les données collectées ne sont pas les mêmes (voir la section suivante).

**Vérifier que chaque URL répond avant de l'inscrire dans App Store Connect.** Une URL
d'assistance morte est un motif de refus, et elle ne se voit pas depuis le dépôt.

## Notes pour l'examen (App Review)

**C'est la section qui décide d'un premier refus.** Tout, dans cette application, est
derrière un compte et un serveur : un examinateur qui l'installe et ne peut pas se
connecter ne voit **rien** — l'écran de connexion demande une adresse de serveur, une
adresse e-mail et une phrase, et il n'y a **ni inscription ni mot de passe oublié dans
l'application**. Sans compte fourni, le refus est certain.

À remplir avant l'envoi :

| Champ | Valeur |
|---|---|
| Serveur à saisir au premier écran | **[à trancher]** — une instance joignable de l'extérieur |
| Compte de démonstration | **[à créer]** |
| Mot de passe / phrase | **pas écrit ici** — voir ci-dessous |

**Le compte doit être amorcé, pas seulement créé.** Un compte vide donne un agenda vide,
une liste de tâches vide, aucune réunion, aucun sondage : l'examinateur verra cinq écrans
blancs et conclura à une application non fonctionnelle. Il faut au minimum, dans
l'organisation du compte : quelques événements sur la journée en cours et les suivantes,
deux ou trois tâches dont une en retard, une réunion réservée à venir, un type de rendez-vous
actif, et un sondage avec des votes. `tools/amorcer_donnees.py` existe dans le dépôt et
est le point de départ ; il n'a pas été éprouvé contre une instance publique.

**La phrase ne figure pas dans le dépôt.** Un secret en clair dans un dépôt reste dans son
historique même retiré, et le balayage de secrets le refuserait à juste titre. Elle est à
coller directement dans App Store Connect.

Texte proposé pour la zone « Notes » :

> GhostCal est un agenda et un outil de prise de rendez-vous auto-hébergé. Le titre, le
> lieu et la description des événements sont chiffrés sur l'appareil ; le serveur conserve
> les horaires, dont il a besoin pour refuser les réservations qui se chevauchent.
>
> Le premier écran demande l'adresse du serveur, puis l'adresse e-mail et la phrase de
> passe. Utilisez le compte fourni ci-dessus — l'application ne propose pas d'inscription,
> les comptes se créent depuis le web.
>
> Une fois connecté, cinq onglets : Agenda, Tâches, Réunions, RDV, Réglages. Le compte
> contient déjà des événements, des tâches, une réunion réservée et un sondage.
>
> Pour éprouver Face ID : Réglages > Sécurité > Verrouiller le coffre, puis rouvrir.
>
> L'application est gratuite et ne contient aucun achat intégré. Elle fonctionne contre
> n'importe quelle instance du serveur, qui est libre — l'adresse se saisit à la
> connexion. L'application ne collecte aucune donnée d'usage et ne contient aucun traceur.

## Confidentialité (questionnaire App Privacy)

**Ne recopiez pas les réponses de GhostPass.** C'est le piège le plus coûteux de cette
fiche, parce que les deux produits se ressemblent et que la réponse est différente.

GhostPass déclare une collecte minimale parce que son serveur n'héberge que des blocs
qu'il ne peut pas ouvrir. Le serveur GhostCal **lit** une partie de ce qu'il stocke, et il
doit le lire. Relevé dans `src/ghostcal/infrastructure/db/models.py` :

| Champ | En base | Le serveur peut-il le lire ? |
|---|---|---|
| `users.email`, `users.name`, `users.timezone` | en clair | **oui** |
| `bookings.start_at` / `end_at` | en clair | **oui** — la contrainte `no_overlap_per_host` l'exige |
| `bookings.invitee_email`, `location`, `meeting_url`, `guest_emails` | `EncryptedString` | **oui** — « chiffré au repos avec la clé de l'application », qu'il détient |
| `bookings.invitee_private` | scellé au X25519 de l'organisation | **non** |
| `users.zk_wrapped_private_key` | enveloppé sous Argon2id | **non** |
| Titre / lieu / description d'un événement, titre / notes d'une tâche | scellés sur l'appareil | **non** |

`EncryptedString` est une protection contre le vol de la base, **pas** une impossibilité de
lecture. La distinction n'est pas rhétorique : Apple demande ce qui est *collecté*, et une
donnée que le serveur déchiffre pour envoyer un courriel est collectée.

Réponses au questionnaire :

| Catégorie | Collecté ? | Pourquoi |
|---|---|---|
| Coordonnées — adresse e-mail | **Oui**, liée, pour le fonctionnement | `users.email` en clair ; l'e-mail des invités déchiffrable par le serveur |
| Coordonnées — nom | **Oui**, liée, pour le fonctionnement | `users.name` en clair, affiché sur la page publique de réservation |
| Contenu utilisateur — autre | **Oui**, lié, pour le fonctionnement | Les rendez-vous : horaires, lieux, liens de visio, réponses des invités |
| Données d'usage, diagnostic | **Non** | Aucun SDK d'analyse, aucun rapport de plantage tiers |
| Identifiants d'appareil, publicité | **Non** | Aucun traceur |
| Localisation | **Non** | Le champ « lieu » est du texte libre, jamais une coordonnée |

**Aucune de ces données n'est utilisée pour du suivi.** L'étiquette obtenue sera « Données
liées à vous », pas « Aucune donnée collectée ».

Ces réponses sont celles du manifeste `apps/mobile/ios/Runner/PrivacyInfo.xcprivacy`, et
les deux doivent rester d'accord : Apple compare.

**Une précision à donner si Apple la demande** : l'instance est celle de l'utilisateur.
Sur une installation auto-hébergée, aucune de ces données ne parvient à l'éditeur.

## Conformité à l'export (chiffrement)

L'application embarque un cœur cryptographique en Rust (`apps/mobile/rust/`), appelé
depuis Dart par flutter_rust_bridge. Ce n'est ni du HTTPS d'appoint ni de
l'authentification seule.

| Question | Réponse | Pourquoi |
|---|---|---|
| L'app utilise-t-elle du chiffrement ? | **Oui** | `deriverCle`, `scellerVers`, `ouvrirSceau`, `dechiffrerSymetrique` sont appelées au premier déverrouillage |
| Chiffrement **propriétaire** ou non publié ? | **Non** | Argon2id (RFC 9106), X25519 (RFC 7748), crypto_box, XChaCha20-Poly1305 (RFC 8439). Le cœur appelle des bibliothèques publiques ; il assemble, il ne chiffre pas |
| Uniquement le chiffrement du système ? | **Non** | Les bibliothèques sont embarquées dans le binaire |
| Uniquement pour l'authentification ? | **Non** | Le contenu des événements est chiffré, pas seulement l'accès |
| Uniquement HTTPS / TLS ? | **Non** | Le scellement est indépendant du transport |
| Disponible en France ? | **Oui** | D'où la déclaration ANSSI |
| Exempté au titre de la note 3 du §740.17(b) ? | **[à trancher avec un juriste]** | Même arbitrage que GhostPass |

`ITSAppUsesNonExemptEncryption` est **délibérément absente** de l'Info.plist, et c'est le
contraire d'un renoncement. `YES` **sans** `ITSEncryptionExportComplianceCode` fait refuser
l'envoi — « Invalid Export Compliance Code (90592) » —, et ce code n'est délivré qu'après
examen d'une documentation qu'App Store Connect ne propose de remplir **qu'une fois un
build reçu**. La boucle ne se ferme pas. Sans la clé, les questions sont posées dans
l'interface à chaque soumission, et les réponses ci-dessus valent exactement ce que valait
la clé. Le contrôle correspondant est dans `tools/ios/archiver-appstore.sh` : il rougit si
la clé réapparaît.

Les obligations restent entières, et elles engagent l'entreprise :

- un rapport d'auto-classification annuel auprès du **BIS** américain, la distribution
  passant par l'App Store ;
- côté français, une **déclaration ANSSI** de fourniture d'un moyen de cryptologie.

GhostPass a rédigé `docs/anssi-dossier-technique.md` pour son propre cœur. **GhostCal n'a
pas d'équivalent**, et celui de GhostPass ne convient pas tel quel : les primitives se
recoupent, mais la gestion des clés et ce que le serveur détient diffèrent — notamment la
rotation par génération d'organisation, absente de GhostPass.

## Le modèle économique, et ce qu'Apple en pensera

L'application est **gratuite**. Deux façons de s'en servir : l'auto-hébergement, le serveur
étant libre ; ou un abonnement qui provisionne à l'abonné sa propre instance.

**Le point à préparer plutôt qu'à découvrir au refus.** L'app ne fonctionne qu'avec un
compte, et l'abonnement se souscrit hors de l'App Store. Apple refuse régulièrement les
applications dont la fonction principale exige un compte payant acquis ailleurs, au titre
de la règle 3.1.1. Deux éléments jouent en faveur de GhostCal, et il faut les énoncer
explicitement dans les notes d'examen :

1. **L'auto-hébergement est gratuit et suffisant.** L'application est pleinement utilisable
   sans rien payer : ce n'est pas une démonstration bridée, il n'y a aucune fonctionnalité
   derrière un paiement.
2. **L'abonnement n'achète pas une fonctionnalité de l'app, mais un hébergement** —
   l'exemption « services multiplateformes » (3.1.3(b)) vise ce cas.

Ce qui reste risqué : l'application ne doit **ni mentionner l'abonnement, ni y renvoyer par
un lien**, faute de quoi la règle 3.1.3(a) s'applique. C'est ce que mesure
`tools/ios/verifier-l-autonomie.sh` sur le paquet livré, et non sur le dépôt. Au
25 septembre, il est **vert** : aucune vitrine, aucun prix, aucun point de terminaison de
l'éditeur en dur — l'adresse du serveur est entièrement saisie par l'utilisateur, et le
seul littéral d'URL de l'application est `https://ghostcal.example.com`, un exemple
réservé par la RFC 2606 qui sert de texte indicatif au champ.

## Captures d'écran

**L'outillage existe et fonctionne ; le jeu livrable, non.** `tools/ios/captures-appstore.sh`
monte un simulateur, y installe l'application, la promène devant l'objectif et mesure
chaque image. Les fichiers produits sont à la taille native — **1320 × 2868**, vérifié —
avec la barre d'état figée à 9 h 41 et l'interface en français.

Ce qui manque n'est plus l'outil : c'est **de quoi photographier**.

App Store Connect réclame **deux jeux** dès lors que l'application se déclare universelle,
ce qui est le cas (`TARGETED_DEVICE_FAMILY = "1,2"`). Un seul jeu laisse la fiche
incomplète.

| Jeu | Appareil | Taille | Dossier |
|---|---|---|---|
| iPhone | iPhone 17 Pro Max (6,9 ") | 1320 × 2868, **relevée à la prise de vue** | `apps/mobile/AppStore/captures/` |
| iPad | iPad Pro 13 " | à relever | `apps/mobile/AppStore/captures-ipad/` |

    ./tools/banc-local.sh              # PostgreSQL jetable + compte amorcé
    ./tools/ios/captures-appstore.sh   # iPhone
    GHOSTCAL_APPAREIL='iPad Pro 13-inch (M4)' ./tools/ios/captures-appstore.sh

### Ce que les premières images ont montré, et qu'aucun contrôle n'aurait vu

Les images produites passent tous les contrôles automatiques : bonne taille, milliers de
teintes, fichier présent. Les **ouvrir** a montré trois choses.

1. **Le banc est un banc d'épreuve, pas une vitrine.** Il amorce délibérément un événement
   scellé sous une autre clé, qui s'affiche en rouge : « Contenu illisible — clé
   manquante ». C'est un comportement juste, et c'est ce qu'on veut éprouver — mais en
   devanture, cela se lit comme un bogue. L'agenda ne porte par ailleurs que deux entrées
   sur une journée, laissant les deux tiers de l'écran vides.

2. **Le nom de calendrier par défaut est en anglais** : « My calendar », venu du serveur.
   Il paraît en clair sur la capture de création d'événement.

3. **Quatre écrans n'avaient aucun fond.** `02-nouvel-evenement` sortait sur fond noir,
   champs blancs, libellés en encre foncée à peine lisibles. J'ai d'abord cru à une
   capture prise en pleine transition et porté l'attente de 600 ms à deux secondes : la
   deuxième image était identique. Ce n'était pas la prise de vue, c'était l'écran.

   Le thème pose `scaffoldBackgroundColor: Colors.transparent` — délibérément, le fond
   étant peint par `FondGhost`. Les cinq onglets en héritent, `EcranDAccueil` les
   enveloppant tous. Mais un écran **poussé** est frère de l'accueil dans la pile, pas son
   enfant : `nouvel_evenement`, `profil`, `sondages` (deux écrans) et `equipe` n'héritaient
   de rien. Corrigé, avec `test/fond_test.dart` qui le garde et qui a été éprouvé par
   mutation dans les deux sens.

   **Aucun test ne le voyait, et c'est le point.** Les champs étaient présents, les
   boutons réagissaient, les valeurs remontaient : tout fonctionnait, seule la peinture
   manquait. Il a fallu ouvrir une image.

**Deux écrans ne sont pas photographiés du tout** : « Réunions » et « Sondages ». Le banc
n'amorce ni réservation ni sondage — mesuré, `/v1/me/meetings` et `/v1/me/polls` rendent
des listes vides. Les photographier donnerait deux états vides en vitrine, ce qui est pire
que deux captures en moins. Les obtenir demande d'étendre `tools/amorcer_donnees.py` : un
sondage se crée par `POST /v1/me/polls` puis se vote par `POST /v1/polls/{slug}/votes` ;
une réservation par `POST /v1/orgs/{slug}/event-types/{slug}/bookings`, ce qui suppose un
horaire de disponibilité que le banc ne pose pas encore.

### Ce qu'il reste à décider avant de verser un jeu

- **Un amorçage de vitrine, distinct de l'amorçage d'épreuve.** GhostPass avait un drapeau
  `--vitrine` pour exactement cette raison. Il faut un agenda plein et plausible, pas un
  agenda qui montre ce qui casse.
- **Le scénario**, et notamment si « Réglages » mérite une des cinq places.
- **Ouvrir chaque image et la regarder.** Les contrôles automatiques distinguent une image
  vide d'une image pleine ; ils ne savent pas dire qu'un texte est **coupé sous la ligne de
  flottaison**. Une section tronquée à mi-ligne a autant de couleurs qu'une section
  entière et se lit comme complète. GhostPass a livré une capture iPad dans cet état.

## Ce qui reste à trancher

Rien de ce qui suit n'est technique — tout engage l'entreprise ou le produit :

- le **sous-titre** (quatre propositions ci-dessus, dont une trop longue d'un caractère) ;
- la **catégorie** principale : Productivité ou Utilitaires ;
- la **classification d'âge**, à confirmer sur le formulaire en vigueur ;
- l'**hébergement d'une politique de confidentialité** qui nomme GhostCal — elle n'existe
  pas, et celle de GhostPass ne convient pas : les données collectées diffèrent ;
- l'**adresse d'assistance** ;
- le **compte de démonstration**, l'instance publique qui le porte, et son amorçage ;
- un **amorçage de vitrine** distinct de l'amorçage d'épreuve, et le scénario de captures ;
- les déclarations **BIS** et **ANSSI**, et le dossier technique qui les accompagne.
