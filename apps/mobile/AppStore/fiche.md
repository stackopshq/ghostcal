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
| **Réparer `POST /v1/auth/register` sur `cal.ghostsuite.cloud`** | Rend `500` pour toute inscription. Sans lui, pas de compte de démonstration — et personne ne peut ouvrir de compte non plus. Diagnostic et identifiants de requête dans « Notes pour l'examen » |
| **Refaire les captures** | Deux commandes ; l'outillage est éprouvé, c'est le `CoreSimulator` de la machine qui a lâché. Voir « Captures d'écran » |
| **Créer le compte de démonstration** | Une commande, dès que le serveur répond : `tools/creer-le-compte-de-revue.sh` |
| **Mettre la page d'assistance en ligne** | `https://ghostsuite.cloud/ghostcal/` rend 404 ; elle s'écrit ailleurs |
| Trancher la **note 3 du §740.17(b)** et mener les démarches BIS et ANSSI | Questions de droit ; GhostPass a le même arbitrage en cours |
| Coller la fiche et répondre au questionnaire de confidentialité | Les réponses exactes sont plus bas, mot pour mot |
| Envoyer l'archive | `tools/ios/archiver-appstore.sh` la construit et la mesure ; l'envoi reste une décision |

Ce qui est prêt : `ExportOptions.plist` ; le manifeste de confidentialité, câblé dans la
cible et **mesuré dans le paquet construit** ; l'outillage d'archive et ses contrôles ; le
contrôle d'autonomie, éprouvé par mutation ; les icônes ; **l'URL de confidentialité**,
vérifiée au contenu et non au code de retour ; **l'application en français et en
anglais** ; l'amorçage de vitrine et le harnais de prise de vue, tous deux éprouvés ; et
les textes ci-dessous.

## Identité

| Champ | Valeur |
|---|---|
| Nom | GhostCal |
| Sous-titre (30 car. max) | **Agenda chiffré, auto-hébergé** (28 car.) |
| Catégorie principale | **Productivité** |
| Catégorie secondaire | Utilitaires |
| Classification d'âge | **4+** |
| Langues | **Français et anglais** |
| Appareils | iPhone **et** iPad (`TARGETED_DEVICE_FAMILY = "1,2"`, relevé dans le projet) |
| Prix | **Gratuit** |

**Le sous-titre retenu : « Agenda chiffré, auto-hébergé » (28 caractères).**

Quatre candidats avaient été proposés. « Votre agenda, sur votre serveur » (31) dépassait
d'un caractère et « Votre agenda sur votre serveur » (30) tenait tout juste — mais aucun
des deux ne dit le chiffrement, qui est l'argument que la concurrence ne peut pas copier.
« Vos rendez-vous, chiffrés » (25) dit le chiffrement et tait l'auto-hébergement.

Le retenu porte **les deux** en vingt-huit caractères : le premier mot dit ce que c'est,
les deux suivants disent pourquoi on le choisirait plutôt que Calendly. Il a de plus
l'avantage de ne rien promettre de faux — l'application affiche elle-même, à l'écran de
création, ce qui est chiffré et ce qui ne l'est pas.

**Classification d'âge — 4+.** L'application ne contient aucun contenu généré par des tiers
et n'ouvre aucun navigateur. Elle affiche des liens de visioconférence saisis par
l'utilisateur, mais ne les ouvre pas : `reunions.dart` les rend en texte. Si le formulaire
d'Apple demande l'accès à du contenu web non filtré, la réponse est non.

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
| **Autres langues que FR et EN** | L'application parle français et anglais. Une langue inconnue retombe sur le **français**, délibérément |

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

| Champ | Valeur | État au 25/09/2026 |
|---|---|---|
| Politique de confidentialité | `https://ghostsuite.cloud/confidentialite/` | **en ligne — à inscrire** |
| Assistance | `https://ghostsuite.cloud/ghostcal/` | **404 — ne pas inscrire encore** |
| Marketing | `https://ghostsuite.cloud/` | en ligne, facultatif |

Les deux premières sont **obligatoires** chez Apple.

**La politique de confidentialité est prête, et elle est juste.** Vérifiée au contenu, pas
au code de retour : la page rend 200, fait 17 682 octets, nomme GhostCal deux fois et porte
la phrase « GhostCal ne peut pas être aveugle, et le dire est plus honnête que de laisser
croire le contraire ». C'est exactement ce que dit le schéma de la base — le serveur lit les
horaires, et il doit les lire. Rien à écrire : on lie cette page telle quelle.

**L'assistance rend un vrai 404**, et c'est vérifié comme tel plutôt que supposé : la page
d'erreur fait 4 382 octets et porte le titre « 404 Page not found · Ghost Suite » —
**exactement** ce que rend un chemin inventé de toutes pièces
(`/ce-chemin-nexiste-pas-xyzzy/`). Sur ces domaines, une redirection peut rendre 200 pour
n'importe quel chemin ; comparer à un témoin absurde est le seul moyen de distinguer une
vraie page d'un attrape-tout. Ici, le 404 est sincère.

La page est en cours d'écriture ailleurs (`suite/site/content/ghostcal.md`). **Ne
l'inscrivez pas avant qu'elle réponde, et vérifiez alors son contenu, pas son code.** Une
URL d'assistance morte est un motif de refus, et une vitrine qui contredirait la liste des
fonctions absentes de cette fiche en est un autre.

## Notes pour l'examen (App Review)

**C'est la section qui décide d'un premier refus.** Tout, dans cette application, est
derrière un compte et un serveur : un examinateur qui l'installe et ne peut pas se
connecter ne voit **rien** — l'écran de connexion demande une adresse de serveur, une
adresse e-mail et une phrase, et il n'y a **ni inscription ni mot de passe oublié dans
l'application**. Sans compte fourni, le refus est certain.

À remplir avant l'envoi :

| Champ | Valeur |
|---|---|
| Serveur à saisir au premier écran | `https://cal.ghostsuite.cloud` |
| Compte de démonstration | `appstore-review@stackops.ch` — **pas encore créé, voir ci-dessous** |
| Mot de passe / phrase | **pas écrit ici** — voir ci-dessous |

**L'instance publique est `cal.ghostsuite.cloud`.** Mesurée : `/api/health` rend
`{"status":"ok","version":"0.1.0"}` et la racine sert bien GhostCal.
`ghostcal.stackops.ch`, qui figure encore dans les tests d'adresse du dépôt, **ne résout
pas**. C'est l'analogue de la bascule de GhostPass vers `pass.ghostsuite.cloud`.

### Le compte n'a pas pu être créé, et ce n'est pas un détail d'outillage

`POST /v1/auth/register` rend **500** sur cette instance, pour toute inscription valide.
Ce n'est pas propre à notre charge : trois tentatives, trois adresses différentes, trois
`500`. Identifiants de requête pour les journaux du serveur :

    612bff7ad468492ea545e720e9fb39a2    appstore-review@stackops.ch
    61c24bcd43e64705b09edc70d17c8482    sonde, clés factices
    e657a502113147e6bd30a26fe55edaa6    même sonde, seconde tentative

**Ce qui est établi**, en resserrant étape par étape :

| Sonde | Résultat | Ce qu'elle élimine |
|---|---|---|
| Mot de passe de 5 caractères | `422 String should have at least 12` | La validation du corps marche |
| « correct horse battery staple » | `422 this password has appeared in a public data breach` | Le contrôle de fuites marche, et il sort donc sur le réseau sans peine |
| Phrase forte, clés factices | **500** | L'échec est **après** la validation |
| `login` sur l'adresse sondée | `401`, et une seconde inscription rend `500` et non `409` | **Aucune ligne n'a été écrite** : la transaction est annulée entière |

L'échec est donc dans `AuthService.register`, après la politique de mot de passe :
`provision_account`, `store_zk_keys`, ou `_send_verification` — cette dernière écrivant un
jeton **puis** appelant le service de courriel (Brevo, `GHOSTCAL_BREVO_API_KEY`). Une clé
absente ou invalide ferait exactement cela. Les journaux du serveur trancheront ; les trois
identifiants ci-dessus les pointent.

**Bonne nouvelle : `appstore-review@stackops.ch` n'est pas immobilisée.** Les identifiants
d'adresse sont uniques et une inscription ratée aurait pu la brûler — vérifié, elle est
libre.

**Une fois le serveur réparé**, une seule commande fait tout :

    GHOSTCAL_PHRASE="$(openssl rand -base64 24)" \
      ./tools/creer-le-compte-de-revue.sh appstore-review@stackops.ch

Elle fabrique les clés avec le cœur Rust, inscrit le compte, **attend** que le lien de
vérification reçu par courriel soit suivi — `login` rend `403 email not verified` tant
qu'il ne l'est pas, et aucun script ne peut franchir cette étape seul —, puis amorce le
jeu de vitrine : huit événements, cinq tâches, trois liens de réservation, un horaire,
trois réunions réservées et un sondage voté. Le même jeu que celui des captures.

**La phrase ne figure pas dans le dépôt** et le script ne l'imprime pas : elle se passe par
l'environnement. Un secret en clair dans un dépôt reste dans son historique même retiré.

**Après publication, changez-la ou supprimez le compte** : elle aura transité par App Store
Connect, dont ce n'est pas le métier de garder des secrets. C'est ce qui a été fait pour
GhostPass.

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

**L'outillage est éprouvé ; le dépôt ne contient aucune image.** Il faut relancer la
prise de vue — deux commandes, un quart d'heure.

`tools/ios/captures-appstore.sh` monte un simulateur, y installe l'application, la promène
devant l'objectif et mesure chaque image. Il a produit **six captures à 1320 × 2868** le
25 septembre, sur le jeu de vitrine, et elles ont été ouvertes et regardées une par une.

Elles ne sont pas versionnées, et c'est délibéré. Le dépôt portait un jeu antérieur, tiré
du **banc d'épreuve** : deux rendez-vous sur la journée, et une ligne rouge « Contenu
illisible — clé manquante » que ce banc dépose exprès pour vérifier qu'elle s'affiche. En
vitrine, cette ligne se lit comme un bogue. Les garder aurait laissé à portée de main des
images plausibles et fausses, ce qui est pire que pas d'images : on les téléverse sans les
regarder. Elles sont donc retirées.

Le jeu de vitrine, lui, n'a pas pu être refait avant la fin de la séance : après une
vingtaine de cycles création/démarrage/suppression, `CoreSimulator` de cette machine a
cessé de répondre — `simctl bootstatus` restant en vie indéfiniment, et `simctl spawn` se
suspendant sur un appareil encore en démarrage. Les deux défauts sont corrigés dans le
script (attente bornée à trois minutes, et l'ordre des appels remis à l'endroit) ; l'état
de la machine, lui, demande un `killall -9 com.apple.CoreSimulator.CoreSimulatorService`
ou un redémarrage.

    ./tools/banc-local.sh --vitrine    # PostgreSQL jetable + jeu de vitrine
    ./tools/ios/captures-appstore.sh   # iPhone 17 Pro Max

| Ordre | Écran | Ce qu'elle montre |
|---|---|---|
| 01 | Agenda | Cinq rendez-vous sur la journée, titres, horaires, lieux |
| 02 | Nouvel événement | Le formulaire **et** la phrase sur ce qui est chiffré — l'argument du produit |
| 03 | Tâches | Les échéances, dont une en retard |
| 04 | Réunions | Trois réservations, avec le nom des invités **déchiffré sur l'appareil** |
| 05 | RDV | Les liens de réservation, actifs et fermés, et le bouton de copie |
| 06 | Réglages | Compte, disponibilités, sécurité — **facultative**, Apple en accepte dix |

La quatrième est celle qui vaut le plus : « Camille Rossier » y paraît parce que le bloc
`invitee_private`, scellé au X25519 de l'organisation, a été ouvert **par l'application**.
Le serveur, lui, ne peut pas le lire. C'est la seule capture qui montre le bout en bout à
l'œuvre plutôt qu'en promesse.

Il manque le **jeu iPad** : l'application se déclare universelle
(`TARGETED_DEVICE_FAMILY = "1,2"`), et App Store Connect réclame alors les deux.

    GHOSTCAL_APPAREIL='iPad Pro 13-inch (M4)' ./tools/ios/captures-appstore.sh

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

- ~~Un amorçage de vitrine, distinct de l'amorçage d'épreuve.~~ **Fait** :
  `./tools/banc-local.sh --vitrine`, qui appelle `tools/amorcer_vitrine.py`. Aucun contenu
  illisible, un horaire de disponibilité, trois réunions réellement réservées depuis la
  page publique, un sondage voté.
- ~~Le scénario.~~ **Fait**, six écrans. Le sixième (Réglages) reste facultatif.
- **Ouvrir chaque image et la regarder.** Fait pour le jeu iPhone ; **à refaire pour
  l'iPad**. Les contrôles automatiques distinguent une image vide d'une image pleine ; ils
  ne savent pas dire qu'un texte est **coupé sous la ligne de flottaison**. Une section
  tronquée à mi-ligne a autant de couleurs qu'une section entière et se lit comme complète.
  GhostPass a livré une capture iPad dans cet état — et c'est justement l'iPad qui manque
  ici.

## Ce qui reste à trancher

Rien de ce qui suit n'est technique — tout engage l'entreprise ou le produit :

- l'**adresse d'assistance**, dès que la page répond ;
- le **jeu iPad** : l'application se déclare universelle, Apple réclame donc deux jeux, et seul celui de l'iPhone est produit. Une commande : `GHOSTCAL_APPAREIL='iPad Pro 13-inch (M4)' ./tools/ios/captures-appstore.sh` — mais **chaque image est à ouvrir** : l'iPad est plus large et plus court, et c'est là que GhostPass a livré une feuille coupée à mi-ligne ;
- garder ou écarter la **sixième capture** (Réglages), Apple en acceptant dix ;
- les déclarations **BIS** et **ANSSI**, et le dossier technique qui les accompagne.
