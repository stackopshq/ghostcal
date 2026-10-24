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

**La 1.6.0 (build 10) est en revue chez Apple depuis le 23 octobre 2026**, état
`WAITING_FOR_REVIEW`, publication en **`AFTER_APPROVAL`** : elle sortira d'elle-même dès
l'accord. C'est le choix de Clara, et il est délibéré — voir plus bas.

Elle remplace la **1.5.0 (build 7)**, retirée de la revue le même jour. Celle-là avait été
soumise le 22 octobre à 18h30 et attendait son tour ; la retirer a coûté sa place dans la
file, et le coût est assumé.

Pourquoi l'avoir retirée plutôt que la laisser passer : le mobile était resté loin derrière
le Mac. La 1.5.0 serait sortie sans la vue Année, sans les barres continues des événements sur
plusieurs jours, sans la création d'un calendrier depuis l'application, et **sans le
correctif de verrouillage** — des écrans empilés restaient affichés, déchiffrés, par-dessus
un agenda verrouillé. Ce dernier point est ce qui a décidé : il ne valait pas une version
d'attente.

**Et un défaut de plus a été trouvé en chemin, par la capture et non par un test.** Le
build 9, déjà déposé, portait une barre d'outils iPad dessinée **sous l'heure et la
batterie** du système. Le correctif précédent préservait bien la marge haute, mais
`_barreDeTitre` rend un `PreferredSize`, et **seul un `AppBar` lit
`MediaQuery.padding.top`** : la marge était là, personne ne la lisait. Mesuré sur
`captures-ipad/01-agenda.png` — le trait du bas tombait à 104 pixels physiques, soit
exactement les 52 points de la barre. D'où le build 10, et les quatre jeux refaits.

**Rien ne garde encore ce correctif.** Le témoin existant éprouve `Mesures.dansLaBarreDeTitre`
en pur, donc il passait avec la barre posée sur l'heure. Un témoin qui morde doit monter la
barre avec une marge haute non nulle et vérifier que sa hauteur l'absorbe — ce qui demande
de l'extraire, puisque `EcranDAccueil` ne se monte pas en test (il exige une session
ouverte, vérifié). Ce défaut a échappé deux fois de suite.

### Une affirmation fausse, et comment elle l'est devenue

Ce paragraphe disait, jusqu'au 23 octobre : « publication réglée sur **manuelle** — rien ne
sortira sans un geste ». **C'était faux.** L'API rend `releaseType=AFTER_APPROVAL` et
`earliestReleaseDate=None` : la version serait sortie **d'elle-même** dès l'accord d'Apple.

Le réglage avait bien été lu `MANUAL` le 22 octobre, avant la soumission. **C'est Clara qui
l'a basculé**, délibérément, parce qu'elle veut une publication automatique. Le document,
lui, continuait d'annoncer le contraire.

Ce premier paragraphe a d'ailleurs commencé par dire « rien ne dit qui l'a changé », en
supposant une dérive entre sessions. C'était faux aussi, et dans un sens qui compte : un
réglage délibéré de la propriétaire du produit s'était fait prendre pour un accident. La
question « qui ? » avait une réponse — il suffisait de la poser.

La leçon est double. **Un état vérifié est vrai à une date, pas pour toujours** : relire
depuis l'API avant de s'en servir est ce qui a évité, le 23, de publier automatiquement une
version qu'on venait de décider de remplacer. Et **un écart entre le dépôt et la réalité
n'est pas forcément un défaut** : ici c'était une décision, et le document avait tort, pas
le réglage.

La 1.6.0 est donc soumise en `AFTER_APPROVAL`, et c'est voulu.

| Ce qu'il reste | Pourquoi ça ne peut pas se faire ici |
|---|---|
| Trancher la **note 3 du §740.17(b)** et mener les démarches BIS et ANSSI | Questions de droit ; GhostPass a le même arbitrage en cours |
| **Promouvoir** sur le Play Store | L'AAB **1.5.0 (7) est déjà sur la piste interne**, déposé le 22 octobre. Ce qui reste est la promotion vers la production, et les droits du compte de service pour cela ne se lisent que dans la console |
| Monter un **AAB 1.6.0 (10)** pour Android | L'iOS part en 1.6.0 (10) ; la piste interne est restée en 1.5.0 (7). Deux plateformes à deux numéros depuis la même source |

Fait : les quatre jeux de captures, déposés et acceptés sans erreur ; la **page
d'assistance**, en ligne et vérifiée au contenu ; la classification d'âge ; la déclaration
des **droits sur le contenu** ; le **texte promotionnel** dans les deux langues ; la
conformité à l'export, cochée **sur le build 7** ; le build monté et distribué en
TestFlight interne.

Tout cela **reste acquis** après le retrait : les captures, les textes, la classification et
les déclarations vivent sur la version, pas sur la soumission. Ce qu'il faut refaire est le
build et la soumission — et la conformité à l'export, qui se coche **par build** et non par
version. C'est le piège de la 1.3.0 : elle avait été soumise avec un build dont la case
n'était pas cochée.

### « Aucun accès Play Console » était faux, et je l'ai écrit deux jours

Cette ligne disait, jusqu'au 24 octobre : « Aucun accès Play Console ni compte de service,
de ce Mac ni de dev-loutre. » **C'est faux, et ça l'était déjà quand je l'ai écrit.**

Le chemin existe et il a servi : `ghostcal-play-publisher@stackops-504008.iam.gserviceaccount.com`,
emprunté depuis la session gcloud de Clara par
`gcloud auth print-access-token --impersonate-service-account=… --scopes=…/androidpublisher`.
Le compte n'a **aucune clé JSON** — une règle d'organisation l'interdit — ce qui explique
qu'un `find` de fichiers de clés ne trouve rien et que j'en aie conclu l'absence d'accès.
C'est par là que la 1.5.0 (7) est montée sur la piste interne le 22 octobre, par
`bundles.upload` puis `tracks/internal`.

L'erreur n'est pas d'avoir cherché au mauvais endroit : c'est d'avoir transformé « je n'ai
rien trouvé » en « il n'y a rien », et de l'avoir **écrit comme un fait** dans le document
qui sert à décider. Le dépôt lui-même portait pourtant l'indice — l'AAB de la piste interne
est cité ailleurs dans ces pages.

Ce qui reste vrai, et qu'il ne faut pas jeter avec le reste :

- **l'API Android Publisher ne crée pas d'application.** Elle gère les versions d'une
  application qui existe déjà. GhostPass n'ayant jamais été déposée, sa fiche demande un
  passage humain dans la console — `applicationId`, classification, Data safety ;
- **les droits de promotion ne se lisent pas depuis gcloud.** Téléverser sur une piste
  interne et publier en production sont deux permissions distinctes, accordées dans
  « Utilisateurs et autorisations ». Seul un essai, ou la console, le dira ;
- **la session gcloud est celle de Clara**, sur la machine de dev-loutre. Elle expire, et
  sa reconnexion lui appartient.

**Le questionnaire App Privacy ne se remplit pas par l'API.** Sept chemins sondés, tous en
404, y compris ceux qu'une application déjà en revue utiliserait : ces réponses ne
s'écrivent que dans l'interface web, sous *Général → Confidentialité de l'app*, et il faut
les **publier** — Apple refuse la soumission avec « you must have published answers », pas
« answers missing ». Des réponses saisies et laissées en brouillon donnent le même refus,
sans le dire.

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

RAPPELS SUR L'APPAREIL
Une notification avant chaque rendez-vous réservé : 5, 10, 15 ou 30 minutes d'avance, à
votre choix. Elle est programmée par l'appareil et non envoyée par le serveur, et elle ne
porte ni le nom de l'invité ni le motif du rendez-vous — seulement l'heure.

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

ON-DEVICE REMINDERS
A notification before each booked meeting: 5, 10, 15 or 30 minutes ahead, as you prefer.
It is scheduled by the device rather than sent by the server, and it carries neither the
invitee's name nor what the meeting is about — only the time.

FACE ID
Face ID or Touch ID reopen your calendar without retyping the passphrase. It is sealed by
the device's hardware: adding a face or a fingerprint invalidates the seal, and GhostCal
tells you so instead of pretending. Auto-lock is configurable — immediately, or after 1,
5 or 15 minutes.

ON YOUR SERVER
You enter your instance's address on the first screen. GhostCal knows no default server
and imposes none.

No trackers. No ads. No behavioural analytics.

**Pourquoi les rappels sont annoncés.** Pas parce que le code existe et que les témoins
passent — c'est vrai des deux et ce n'aurait pas suffi. Parce qu'un rappel a **sonné sur
un vrai téléphone**, constaté le 22 octobre. Une première tentative n'avait rien produit,
et la cause était le jeu de données, non le produit : aucun rendez-vous réservé dans les
sept jours de l'horizon de programmation. Un rappel qui ne sonne pas faute de rendez-vous
est indiscernable d'un rappel cassé, et c'est exactement le doute qu'un utilisateur ne
peut pas lever seul.

## À ajouter à la description, à la prochaine version

La description déposée est **en revue** et ne peut plus bouger avant le verdict. Elle est
juste — elle ne promet rien que l'app ne tienne — mais elle est devenue **incomplète**, et
ce qui manque sont des arguments de vente :

- les **cinq vues** d'agenda : jour, semaine, mois, liste, année ;
- la **mise en page de tablette** : colonne latérale, mini-mois, événement ouvert à côté
  de la grille ;
- le **renommage d'un calendrier**, et le fait que le calendrier par défaut porte
  désormais le nom de la langue du compte ;
- la **création** de sondages, de types de rendez-vous et d'horaires, et l'**invitation**
  d'un membre dans l'équipe — trois choses que l'ancienne description renvoyait au web ;
- la **photo de profil**, qu'on peut ajouter et plus seulement retirer.

Le texte promotionnel, lui, se change **sans soumettre de version** : c'est le seul levier
disponible d'ici au verdict.

## Ce que la description ne dit pas, délibérément

Cette liste est la contrepartie de la précédente. Chaque ligne est une fonctionnalité que
les concurrents annoncent, que GhostCal **n'a pas** dans son application iOS, et qu'il
serait tentant d'écrire.

**Relue ligne à ligne contre le code le 22 octobre 2026, et cinq lignes sont tombées.**
C'est la dérive attendue d'une liste de ce genre : elle a été écrite le 25 septembre, le
produit a avancé, et une absence cesse d'être vraie sans que personne pense à rouvrir le
document. Le danger n'est pas qu'elle sous-vende — c'est qu'on la croie. Les lignes
retirées sont consignées plus bas plutôt qu'effacées, pour qu'on puisse vérifier qu'elles
l'ont été à bon droit.

| Absent | Vérifié |
|---|---|
| **Tout est chiffré** | Faux. Horaires, fuseaux, adresses e-mail, noms de calendriers, titres de réunions et lieux partent en clair. Seuls le titre/lieu/description d'un événement et le titre/notes d'une tâche sont scellés. L'application le dit elle-même à l'écran de création |
| **Accès hors ligne** | Aucun cache, aucune base locale, aucune file de synchronisation. Sans réseau, rien ne s'affiche |
| **Invitation de participants à un événement** | L'écran de création n'a pas ce champ |
| **Création d'un événement récurrent** | Aucun champ de répétition à la création. Une série **existante** se modifie, mais d'un bloc : l'écran dit « vos modifications s'appliquent à toute la série ; pour n'en changer qu'un, passez par le web » |
| **Changement de mot de passe ou de phrase** | Aucun écran ne l'offre — vérifié par recherche sur `lib/`. La justification d'origine disait que `chiffrerSymetrique` n'était appelée nulle part ; **c'est faux depuis** qu'elle sert à sceller la clé d'organisation d'une invitation d'équipe. La conclusion tient, son motif non : la bonne preuve est l'absence d'écran, pas l'absence d'appel |
| **Import / export** | Aucun |
| **Autres langues que FR et EN** | L'application parle français et anglais. Une langue inconnue retombe sur le **français**, délibérément |

### Les cinq absences qui n'en sont plus

Retirées du tableau le 22 octobre, chacune après avoir retrouvé dans le code ce qui la
dément. Elles sont listées ici pour que la correction se vérifie, et parce qu'une ligne
qui disparaît sans trace laisse penser qu'elle n'a jamais existé.

| Ce que la fiche affirmait | Ce que le code dit |
|---|---|
| « L'agenda est en **jour unique** » | `VueDAgenda` compte cinq valeurs — jour, semaine, mois, liste, année — et le sélecteur paraît sur les captures iPad. **C'est la seule des cinq qui contredisait une image livrée** |
| « Création de sondages, de types de rendez-vous, d'horaires : consultation seulement » | `EcranDeNouveauSondage` depuis `sondages.dart`, `nouveauType` depuis `types_de_rendez_vous.dart`, et `_ouvrirLHoraire(null)` depuis les réglages — les trois se créent |
| « Aucun bouton d'invitation » dans l'équipe | `equipe.dart` appelle `Reglages.inviter`, qui scelle la clé d'organisation sous une clé de lien que le serveur ne voit pas (ADR-0003) |
| « Photo de profil : on peut la retirer, jamais l'ajouter » | `profil.dart` appelle `televerserLaPhoto` |
| « Les occurrences d'une série sont **non modifiables** » | Elles le sont, d'un bloc. Seule la modification d'une occurrence isolée renvoie au web |

**Un point à assumer plutôt qu'à découvrir en revue, et il s'est beaucoup allégé.**
Quelques fonctions renvoient encore au web — la création d'un compte, celle d'une série
récurrente, la modification d'une occurrence isolée. Un examinateur peut y voir une app
« incomplète » au titre de la règle 4.2 sur le contenu minimal. Les notes d'examen mettent
donc en avant ce que l'app fait **seule**, et la liste a grandi : créer et modifier des
événements, gérer des tâches, annuler des réunions, créer et basculer des liens de
réservation, créer et arbitrer des sondages, poser ses horaires de disponibilité,
renommer ses calendriers, inviter un membre et administrer les rôles. C'est un usage
entier, pas une télécommande.

## Mots-clés (100 caractères, virgules comprises)

```
agenda,rendez-vous,chiffré,calendrier,réservation,planning,vie privée,rappels,réunion
```

**L'anglais aussi** : `calendar,scheduling,encrypted,booking,privacy,self-hosted,reminders,meeting`
(75 caractères), où « reminders » a pris la place de « team », pour la même raison.

85 caractères. « équipe » a cédé sa place à « rappels » : les rappels sont désormais
programmés par l'appareil, et c'est une fonction qu'on cherche ; la gestion d'équipe se
réduit, dans l'app, à consulter des rôles. Le nom de l'app et les catégories sont déjà indexés : les répéter ici
gaspillerait la limite. Les marques concurrentes n'y figurent pas — Apple les refuse.

**Ce qui a été retiré, et pourquoi.** « hors ligne » : l'application n'a aucun mode hors
ligne. « notifications » : le pluriel promettrait plus que l'unique
notification de rendez-vous qui existe. « synchronisation » : il n'y a ni cache ni fusion, seulement des appels réseau.
Un mot-clé qui promet une fonctionnalité absente se paie à la revue, et déçoit celui qui
installe pour ça.

## Nouveautés de cette version

```
Première version.
```

## URL

| Champ | Valeur | État au 21/10/2026 |
|---|---|---|
| Politique de confidentialité | `https://ghostsuite.cloud/confidentialite/` | **en ligne — à inscrire** |
| Assistance | `https://ghostsuite.cloud/ghostcal/` | **en ligne — à inscrire** |
| Marketing | `https://ghostsuite.cloud/` | en ligne, facultatif |

Les deux premières sont **obligatoires** chez Apple.

**La politique de confidentialité est prête, et elle est juste.** Vérifiée au contenu, pas
au code de retour : la page rend 200, fait 17 682 octets, nomme GhostCal deux fois et porte
la phrase « GhostCal ne peut pas être aveugle, et le dire est plus honnête que de laisser
croire le contraire ». C'est exactement ce que dit le schéma de la base — le serveur lit les
horaires, et il doit les lire. Rien à écrire : on lie cette page telle quelle.

**L'assistance est en ligne depuis**, et vérifiée de la même façon : la page rend 200,
fait 18 202 octets et porte le titre « GhostCal, agenda et prise de rendez-vous · Ghost
Suite ». Le contrôle qui rend la mesure concluante est le témoin : `/ce-chemin-nexiste-pas-xyzzy/`
rend toujours **404**, donc ce domaine ne sert pas un attrape-tout qui rendrait 200 pour
n'importe quoi. Au 25 septembre, cette même page rendait un 404 sincère ; c'est la seule
ligne de cette fiche qui est passée du rouge au vert sans qu'on touche au dépôt.

## Notes pour l'examen (App Review)

**C'est la section qui décide d'un premier refus.** Tout, dans cette application, est
derrière un compte et un serveur : un examinateur qui l'installe et ne peut pas se
connecter ne voit **rien** — l'écran de connexion demande une adresse de serveur, une
adresse e-mail et une phrase, et il n'y a **ni inscription ni mot de passe oublié dans
l'application**. Sans compte fourni, le refus est certain.

À remplir avant l'envoi :

| Champ | Valeur |
|---|---|
| Serveur à saisir au premier écran | `cal.ghostsuite.cloud` — **sans suffixe** |
| Compte de démonstration | `dev.web@stackops.ch` — **créé, vérifié et amorcé** ; c'est celui qui sert déjà à la revue Google Play |
| Mot de passe / phrase | **pas écrit ici** — voir ci-dessous |

**L'instance publique est `cal.ghostsuite.cloud`, sans suffixe.** Mesurée le
2026-10-21, méthode par méthode plutôt que sur la seule racine : `POST /v1/auth/login`
rend **422** — la route existe et valide son corps —, `GET /v1/me/organizations` rend
**401**, et les mêmes chemins sous `/api` rendent **404**. Le préfixe `/api` ne sert plus
que le `health` du site web (`{"status":"ok","version":"0.1.0"}`). **C'est l'inverse de ce
que disait cette fiche au 25 septembre**, et l'inversion compte : un examinateur qui
saisirait `https://cal.ghostsuite.cloud/api` tomberait sur « cette adresse ne sert pas
l'API » dès la connexion. L'adresse à inscrire ne porte donc **aucun** suffixe.
`ghostcal.stackops.ch`, qui figure encore dans les tests d'adresse du dépôt, **ne résout
pas**. C'est l'analogue de la bascule de GhostPass vers `pass.ghostsuite.cloud`.

### Le compte de démonstration, et les trois murs franchis pour l'obtenir

Créé sur `dev.web@stackops.ch`, vérifié, et amorcé sans un refus : huit
événements, cinq tâches, trois types de rendez-vous, un horaire, trois réunions réservées
et un sondage voté — le serveur confirme ses propres comptes. C'est le jeu que
photographient les captures.

Le parcours a buté sur trois choses, et chacune se présentait comme autre chose qu'elle
n'était. Elles sont consignées ici parce qu'aucune n'est propre à GhostCal.

**1. `register` rendait `500`.** Brevo refusait l'envoi — `401`, l'adresse de sortie du
serveur n'était pas encore autorisée chez lui — et l'exception remontait jusqu'à faire
annuler la transaction. L'échec ressemblait donc à un défaut d'inscription alors que
c'était un défaut d'envoi de courriel. Résolu le jour même côté exploitation. La
fragilité de conception qu'il révélait — l'inscription dépendant d'un tiers synchrone —
est traitée séparément : l'envoi passe désormais par le worker.

**2. Le lien de vérification menait à `localhost:3001`.** L'instance tournait sans
`GHOSTCAL_FRONTEND_BASE_URL` et retombait sur la valeur de développement. L'inscription
réussissait, le courriel partait, et **seul le destinataire voyait la panne**. Le serveur
n'enregistrait rien. Corrigé côté exploitation, et un validateur refuse désormais de
démarrer sur une adresse locale hors développement.

**3. L'API vivait alors sous `/api` — elle est passée à `/v1` depuis.** `$API/v1/me/organizations` ne rend pas une erreur : il rend
**la page HTML du client, avec un code 200**. Le script concluait « le compte n'est pas
exploitable » — en accusant le compte. Deux chemins masquaient le défaut, `register` et
`login` fonctionnant nus car relayés par le client. La spécification servie à
`/api/openapi.json` fait foi.

**Et un quatrième, le plus discret : Cloudflare bannit la signature de `Python-urllib`**
— `403 error code: 1010`, vingt-trois refus d'affilée sur l'amorçage. Le message ne parle
ni d'agent utilisateur ni de signature, donc on cherche du côté du jeton. La même leçon
était écrite dans la fiche de GhostPass depuis des semaines ; elle n'avait pas traversé.

**Refaire ou déplacer le compte** tient en une commande :

    GHOSTCAL_PHRASE='…' ./tools/creer-le-compte-de-revue.sh <adresse>

Elle fabrique les clés avec le cœur Rust, inscrit, **attend** que le lien reçu par
courriel soit suivi — aucun script ne franchit cette étape seul, et c'est voulu : un
compte qu'un script vérifierait seul ne prouverait rien de l'adresse — puis amorce la
vitrine.

**Choisissez une adresse dont vous savez lire la boîte.** `appstore-review@stackops.ch`
n'existe pas ; une première inscription y a été lancée sans le vérifier, et le courriel
est parti dans le vide. Le compte résiduel, non vérifié et vide, est à supprimer côté
serveur.

**Ce que les notes de revue disaient encore le 22 octobre, et qui aurait coûté un refus
certain.** Elles donnaient à l'examinateur `cal.ghostsuite.cloud/api` comme adresse et
`contact@stackops.ch` comme identifiant. Les deux étaient faux : l'API a déménagé sous
`/v1` à la racine, et le compte de démonstration est `dev.web@stackops.ch` — ce que le
champ « compte de démonstration » d'App Store Connect disait déjà, en contredisant les
notes placées juste à côté. Un examinateur qui suit les notes ne se connecte pas, ne voit
que l'écran de connexion, et refuse.

Corrigé, et **vérifié plutôt que supposé** : `POST https://cal.ghostsuite.cloud/v1/auth/login`
avec les identifiants de revue rend **200** et quatre jetons. Les mêmes chemins sous `/api`
rendent 404.

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
> Une fois connecté, l'application ouvre sur la journée. La barre du bas porte, de gauche
> à droite : un bouton de menu, la vue courante, la recherche, et un bouton « + » qui crée
> un événement. Le menu donne les autres sections — Tâches, Réunions, RDV, Réglages — et
> les autres vues de l'agenda. Le compte contient déjà des événements, des tâches, trois
> réunions réservées et un sondage.
>
> **La mention « cinq onglets » a été retirée le 22 octobre** : la refonte de l'agenda a
> remplacé la barre d'onglets par une barre flottante et un menu. Un examinateur qui
> cherche des onglets ne les trouve pas, et conclut que l'application est incomplète.
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

**Refaites le 2026-10-21, sur le jeu de vitrine, et regardées une par une.** Cette dernière
phrase est le contrôle qui compte : l'outil mesure les dimensions et compte les teintes,
ce qui distingue une image vide d'une image pleine — et rien d'autre. Il ne sait pas dire
qu'un texte est coupé. Une section tronquée à mi-ligne a autant de couleurs qu'une section
entière.

    ./tools/banc-local.sh --vitrine    # PostgreSQL jetable + jeu de vitrine
    ./tools/ios/captures-appstore.sh   # iPhone 17 Pro Max, 1320 × 2868

**Quatre jeux, pas un.** La fiche est déclarée bilingue et l'application universelle :
App Store Connect réclame alors un jeu **par langue et par famille d'appareils**, et
refuse la soumission s'il en manque un. Les quatre commandes, à lancer **l'une après
l'autre** — deux passes simultanées se disputent le port 3122 du pilote, et la seconde
échoue sur un message qui ne parle pas de port :

    ./tools/ios/captures-appstore.sh
    GHOSTCAL_LANGUE=en ./tools/ios/captures-appstore.sh
    GHOSTCAL_APPAREIL='iPad Pro 13-inch (M4)' ./tools/ios/captures-appstore.sh
    GHOSTCAL_LANGUE=en GHOSTCAL_APPAREIL='iPad Pro 13-inch (M4)' ./tools/ios/captures-appstore.sh

Elles atterrissent dans `captures/`, `captures-en/`, `captures-ipad/` et
`captures-ipad-en/` — un répertoire par jeu, pour que la seconde passe n'écrase pas la
première. Découvrir l'écrasement devant App Store Connect coûte une soumission.

### Trois défauts que seuls des yeux ont vus, le 21 octobre

Les jeux produits ce matin passaient tous les contrôles — bonnes dimensions, des centaines
de teintes, aucune image vide. Les ouvrir a montré trois choses, et elles valent d'être
écrites parce qu'aucune n'était détectable autrement.

**1. L'agenda s'ouvrait sur une soirée vide.** La refonte de l'agenda ouvre la grille à
l'heure courante, ce qui est juste pour un utilisateur. Les prises se faisant vers 20 h 45,
la capture montrait 15 h–23 h : **un rendez-vous et demi dans les deux tiers d'un écran
vide**, le premier amputé de son titre, le dernier coupé par la barre. Le scénario recadre
désormais sur 8 h avant de déclencher. La journée montre ses cinq entrées.

**2. Le clavier mangeait l'argument du produit.** Le champ de saisie rapide est en
`autofocus`, et le clavier logiciel recouvrait tout ce qui suit « Début » — donc la phrase
« le titre, le lieu et la description sont chiffrés sur cet appareil », seule raison de
montrer cet écran. En anglais, le simulateur y ajoutait son didacticiel de frappe glissée,
bouton « Continue » compris. Le scénario rend le focus avant de photographier.

**3. Une capsule noire à la place de l'Îlot dynamique, sur cette seule vue.** Mesuré plutôt
que supposé : 88,6 % de pixels noirs dans la bande centrale du haut de `02`, **0,0 % sur
les onze autres images**, dans les deux langues, et rien sur iPad. L'écran de création
change le style de la barre d'état par le canal natif ; iOS redessine la vraie barre et
l'habillage de `simctl` est perdu là. L'heure figée à 9 h 41 survivait, ce qui rendait la
perte invisible à un contrôle qui aurait regardé l'horloge. L'habillage est maintenant
reposé avant **chaque** déclenchement.

### Ce que les captures anglaises ont révélé du produit

**Les données suivaient le français alors que l'interface suivait l'anglais.** L'amorçage
de vitrine est désormais bilingue (`GHOSTCAL_LANGUE`), et `captures-appstore.sh` refuse de
démarrer si le banc n'est pas amorcé dans la langue de la prise de vue — il compare le
titre du premier type de rendez-vous. Photographier des libellés d'une langue au-dessus
des données de l'autre ne se voit sur aucune mesure.

**Reste un défaut qui n'est pas le mien : le calendrier par défaut s'appelle « Mon
agenda » pour tout le monde.** Le nom est écrit en dur dans
`src/ghostcal/infrastructure/db/calendar_repository.py`, et `PATCH /v1/calendars/{id}` ne
change que la **couleur** : un utilisateur anglophone ne peut pas le renommer. Il paraît
tel quel sur la capture anglaise `02`, et il y reste — maquiller l'image donnerait une
vitrine que le produit ne tient pas. **C'est un correctif serveur à faire**, pas un
réglage de prise de vue.

**Le correctif est en cours ailleurs** (`fix/rename-calendars`, 22 octobre), et il ne fait
que **la moitié** du chemin — la moitié qui manquait, mais la moitié seulement.

`PATCH /v1/me/calendars/{id}` accepte désormais un `name`, donc un anglophone peut
renommer son calendrier. En revanche `name="Mon agenda"` reste écrit en dur dans
`calendar_repository.py` : **tout nouveau compte, quelle que soit la langue, part encore
d'un nom français**. Une première version de cette note annonçait que la capture anglaise
`02` deviendrait périmée ; c'est faux, et l'erreur venait de moi. Elle reste exacte, parce
que c'est exactement ce qu'un anglophone voit en arrivant.

Reste donc un choix, et il est de produit, pas de prise de vue :

1. **Laisser le défaut par défaut** et photographier ce qui est. Honnête, et un peu rude.
2. **Renommer le calendrier dans l'amorçage anglais** — ce que le produit permet
   maintenant, donc une vitrine qu'il tient. Deux passes à refaire et deux jeux à
   redéposer :

        GHOSTCAL_LANGUE=en ./tools/banc-local.sh --vitrine
        GHOSTCAL_LANGUE=en ./tools/ios/captures-appstore.sh
        GHOSTCAL_LANGUE=en GHOSTCAL_APPAREIL='iPad Pro 13-inch (M4)' ./tools/ios/captures-appstore.sh

3. **Nommer le calendrier par défaut selon la langue du compte**, côté serveur. Le vrai
   correctif, et le seul qui épargne la question au prochain utilisateur plutôt qu'au
   prochain photographe.

### Les cinq à livrer

| Ordre | Écran | Ce qu'elle montre |
|---|---|---|
| 01 | Agenda | Cinq rendez-vous sur la journée, titres, horaires, lieux |
| 02 | Nouvel événement | Le formulaire **et** la phrase sur ce qui est chiffré — l'argument du produit, complet et non tronqué |
| 03 | Tâches | Cinq échéances, dont une en retard, en rouge |
| 04 | Réunions | Trois réservations, avec le nom des invités **déchiffré sur l'appareil** |
| 05 | RDV | Deux liens actifs, un fermé, et le bouton de copie |

**La quatrième est celle qui vaut le plus.** « Camille Rossier » y paraît parce que le bloc
`invitee_private`, scellé au X25519 de l'organisation, a été ouvert **par l'application**.
Le serveur ne peut pas le lire. C'est la seule capture qui montre le bout en bout à
l'œuvre plutôt qu'en promesse.

### La sixième est produite mais **ne doit pas être livrée**

`06-reglages` porte deux défauts, tous deux invisibles aux contrôles automatiques :

- **« Heures de bureau » est coupé en plein milieu de sa ligne** sous la barre d'onglets.
  C'est exactement le défaut que GhostPass a livré sur une capture iPad.
- Le serveur affiché est `127.0.0.1:8099`, l'adresse du banc. Ce n'est pas faux, mais ça
  annonce un banc d'essai sur une devanture.

Apple en accepte dix et n'en exige pas six. Cinq racontent le produit ; celle-là n'ajoute
qu'une liste de réglages, et au prix d'un texte tronqué.

### Le jeu iPad, et la question de produit qu'il posait

    GHOSTCAL_APPAREIL='iPad Pro 13-inch (M4)' ./tools/ios/captures-appstore.sh

Six images en 2064 × 2752. **La question est tranchée, et elle l'a été par le travail
macOS, pas par un arbitrage de vitrine.**

Au 25 septembre, c'était une mise en page de téléphone étirée sur une tablette : des
champs de saisie de deux mille pixels de large pour y écrire un titre, des listes perdues
dans une page aux deux tiers vide. Cette fiche posait deux voies — retirer `"2"` de
`TARGETED_DEVICE_FAMILY` pour cesser de promettre, ou adapter la mise en page, « un vrai
chantier ».

Le chantier a été fait ailleurs. La refonte de bureau vit dans du code Flutter **partagé**,
et l'iPad en hérite : une colonne latérale avec les sections, les calendriers et un
mini-mois, un sélecteur de vues, et un événement qui s'ouvre à côté de la grille au lieu
de la recouvrir. Au-dessus de 900 points de large, l'application change de forme ; un iPad
Pro 13 pouces en fait 1032.

Déclarer `"1,2"` n'est donc plus une promesse qu'on ne tient pas. **Le seuil est aussi ce
qui rend les captures iPad fragiles** : elles photographient une disposition que seule la
largeur déclenche, et un scénario écrit pour le téléphone s'y casse sans le dire. Les deux
passes du 22 octobre ont échoué pour cette raison exacte — voir plus haut.

### Pourquoi les images du dépôt sont celles-ci et pas d'autres

Le dépôt portait un jeu antérieur tiré du **banc d'épreuve** : deux rendez-vous, et une
ligne rouge « Contenu illisible — clé manquante » que ce banc dépose exprès pour vérifier
qu'elle s'affiche. En vitrine, cette ligne se lit comme un bogue. Elles ont été retirées :
des images plausibles et fausses à portée de main sont pires que pas d'images, parce qu'on
les téléverse sans les regarder.

**Les cinq versionnées ici sont celles à téléverser.** Elles vieilliront dès que
l'interface bougera — les refaire est deux commandes, et il faut les refaire plutôt que de
les croire.


## Ce qui reste à trancher

Rien de ce qui suit n'est technique — tout engage l'entreprise ou le produit. Trois
points de la liste du 25 septembre en sont sortis depuis : l'adresse d'assistance répond,
le jeu iPad est produit dans les deux langues, et la sixième capture est **écartée** —
voir plus bas pourquoi.

- les déclarations **BIS** et **ANSSI**, et le dossier technique qui les accompagne.
