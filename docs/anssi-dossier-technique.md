# Dossier technique — moyen de cryptologie GhostCal

Annexe technique destinée à la **déclaration de fourniture d'un moyen de cryptologie**
auprès de l'ANSSI.

## Avertissement sur ce que ce document est, et n'est pas

Il décrit **ce que le code fait**, relevé dans le dépôt, avec les versions et les
paramètres exacts. Chaque affirmation ci-dessous est vérifiable dans les fichiers cités.

Il ne prétend **pas** :

- épouser la structure du formulaire ANSSI en vigueur. Il faut le reporter sur le
  formulaire courant, section par section ;
- trancher la qualification juridique. GhostCal assure une fonction de confidentialité,
  mais **partiellement** — voir §4, qui est la section à lire en premier si l'on vient de
  GhostPass ;
- couvrir l'export. **Fournir n'est pas exporter**, et la distribution par l'App Store et
  Google Play atteint le monde entier. Question distincte, à poser avec.

### Ce document n'est pas celui de GhostPass

Les deux produits partagent le même cœur cryptographique et **divergent sur trois points
qui changent la déclaration**. Les recopier l'un sur l'autre serait faux :

| | GhostPass | GhostCal |
|---|---|---|
| Parallélisme Argon2id | 4 | **1** |
| Sel de dérivation | déterministe, SHA-256 de l'adresse | **aléatoire, 16 octets**, rangé auprès de l'enveloppe |
| Le serveur lit-il du contenu ? | non | **oui, une partie** — §4 |
| Rotation des clés | — | **par génération d'organisation** |

## 1. Objet

GhostCal est un agenda et un outil de prise de rendez-vous. Le titre, le lieu et la
description des événements, ainsi que le titre et les notes des tâches, sont chiffrés sur
l'appareil de l'utilisateur. **Les horaires ne le sont pas**, et ne peuvent pas l'être :
le serveur doit savoir quand un hôte est occupé pour refuser une réservation qui se
chevauche, et pour envoyer les rappels par courriel.

C'est une connaissance nulle **partielle**, et assumée comme telle : l'application
l'affiche elle-même à l'écran de création d'un événement.

Distribué sous **Elastic License 2.0**, et **auto-hébergeable** : l'éditeur n'est pas un
passage obligé. L'adresse du serveur se saisit au premier écran.

Formes de mise à disposition : application iOS (App Store), application Android (Google
Play), application web, et serveur auto-hébergeable.

## 2. Fonctions cryptographiques mises en œuvre

Le cœur est unique, écrit en Rust — `suite/crates/ghost-crypto` —, partagé par toutes les
applications au moyen de liaisons générées (UniFFI pour Swift et Kotlin, WebAssembly pour
le web, flutter_rust_bridge pour Dart). **Il n'existe pas de seconde implémentation.**

| Fonction | Primitive | Paramètres | Fichier |
|---|---|---|---|
| Dérivation depuis la phrase secrète | **Argon2id** (v0x13) | 65 536 Kio, 3 passes, **parallélisme 1**, sortie 32 octets | `zk.rs` (`deriver_cle`) |
| Sel de dérivation | **aléatoire** | 16 octets, tiré par `OsRng`, rangé auprès de l'enveloppe | `zk.rs` (`sel_aleatoire`) |
| Enveloppe de contenu, format courant | **XChaCha20-Poly1305** | clé 256 bits, nonce **192 bits** (24 octets), marqueur `v: 1` | `zk.rs` |
| Enveloppe de contenu, format web ancien | **AES-256-GCM** | clé 256 bits, nonce 96 bits, **sans champ `v`** | `zk.rs` (`decrypt_legacy`) |
| Accord de clés | **X25519** | — | `keys.rs` |
| Dérivation de la clé de sceau | **HKDF-SHA-256** | sel vide, **info = le domaine** | `zk.rs` (`cle_aead`) |
| Séparation des produits | chaîne de domaine | `ghostcal-zk-v1` | passé en paramètre, jamais constante |
| Chiffrement au repos côté serveur | **Fernet** (AES-128-CBC + HMAC-SHA-256) | clé détenue par le serveur | `infrastructure/db/types.py` |

La séparation de domaine est **un paramètre et non une constante** : un sceau de GhostCal
ne s'ouvre pas avec le domaine de GhostMail, et un témoin l'éprouve
(`le_domaine_separe_les_produits`).

### Lecture de l'ancien format

Le dispatch se fait sur le marqueur de version : une enveloppe portant `v: 1` est lue en
XChaCha20-Poly1305, une enveloppe **sans** `v` est lue comme l'ancien format web
(AES-256-GCM). **Rien n'écrit plus l'ancien format.** La dérivation est identique dans les
deux ; seul l'AEAD final diffère. Les vecteurs de non-régression viennent de WebCrypto
exécutant l'ancien client, et non du cœur — `crates/ghost-crypto/tests/legacy_web.rs`.

### Bibliothèques tierces

`argon2 0.5`, `chacha20poly1305 0.10`, `aes-gcm 0.10`, `crypto_box 0.9`, `x25519-dalek 2.0`,
`hkdf 0.12`, `sha2 0.10`, `zeroize 1.9`, `rand_core 0.6` (entropie du système par
`getrandom`). Implémentations publiques et auditables ; **aucun algorithme n'a été écrit
pour ce produit**.

## 3. Gestion des clés

La phrase secrète ne quitte jamais l'appareil. Elle dérive, par Argon2id et un sel
aléatoire, la clé qui déballe la **clé privée de l'organisation**. Le contenu des
événements est scellé vers la **clé publique de l'organisation** ; tout membre qui détient
la clé privée correspondante peut l'ouvrir.

**Rotation par génération.** `organizations.zk_key_generation` compte les générations, et
chaque enregistrement scellé porte celle qui l'a scellé. Une rotation n'oblige donc pas à
rechiffrer l'existant : les anciennes générations restent lisibles, et le client choisit la
bonne clé d'après le marqueur. C'est la différence structurelle avec GhostPass, qui n'a pas
cette notion.

**Récupération.** Une phrase de récupération distincte enveloppe la même clé privée sous un
second sel, afin qu'une phrase oubliée ne condamne pas l'organisation.

**Conservation sur l'appareil.** Sur iOS, trousseau système avec
`kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly` et, pour le déverrouillage biométrique,
`.biometryCurrentSet` — l'entrée est invalidée dès qu'une biométrie est enrôlée. Sur
Android, `AndroidKeyStore`, biométrie forte seule, `setInvalidatedByBiometricEnrollment`.
Ces garanties sont éprouvées **sur matériel** et non déduites
(`integration_test/biometrie_trois_etats_test.dart`), parce qu'un trousseau qui ignore une
contrainte ne le signale pas.

## 4. Ce que le serveur détient — et ce qu'il lit

**C'est la section qui distingue GhostCal de GhostPass, et elle doit être lue telle
quelle : le serveur GhostCal lit une partie de ce qu'il stocke, et il doit le lire.**

| Donnée | En base | Le serveur peut-il la lire ? |
|---|---|---|
| `users.email`, `users.name`, `users.timezone` | en clair | **oui** |
| `bookings.start_at` / `end_at` | en clair | **oui** — la contrainte `no_overlap_per_host` l'exige |
| `bookings.invitee_email`, `location`, `meeting_url`, `guest_emails` | `EncryptedString` | **oui** — chiffré au repos avec **la clé du serveur** |
| `bookings.invitee_private` | scellé vers la clé publique de l'organisation | **non** |
| `users.zk_wrapped_private_key` | enveloppé sous Argon2id | **non** |
| Titre, lieu, description d'un événement ; titre et notes d'une tâche | scellés sur l'appareil | **non** |

`EncryptedString` protège contre le **vol de la base**, pas contre le serveur lui-même :
la clé est dans sa configuration. La distinction n'est pas rhétorique — une donnée que le
serveur déchiffre pour envoyer un courriel est une donnée collectée, et la déclaration de
confidentialité publiée le dit ainsi plutôt que d'annoncer « aucune donnée collectée ».

Sur une installation **auto-hébergée**, aucune de ces données ne parvient à l'éditeur.

## 5. Transport

HTTPS/TLS entre les applications et le serveur, assuré par l'hébergement. Le scellement
est **indépendant du transport** : il protège le contenu y compris d'un serveur compromis,
ce que TLS ne fait pas. L'application refuse d'ailleurs une adresse de serveur en clair
hors boucle locale (`modeles/adresse.dart`).

## 6. Interopérabilité

Quatre implémentations clientes consomment le même cœur : Rust, Swift, Kotlin, Dart, et
WebAssembly pour le navigateur. Les vecteurs croisés vivent dans
`crates/ghost-crypto/tests/` ; celui qui compte le plus,
`la_derivation_reproduit_celle_du_navigateur`, vient de `hash-wasm` — la bibliothèque
Argon2 du navigateur — et non du cœur : il vérifie que les clients obtiennent ce que le web
obtient, et non que le cœur est cohérent avec lui-même.

## 7. À compléter avant dépôt

Éléments qui ne se tirent pas du code et relèvent de l'éditeur :

- Identification du déclarant : StackOps, entreprise individuelle de Kevin Allioli, siège à
  Saint-Julien-en-Genevois (Haute-Savoie).
- Version exacte et date de la mise à disposition déclarée. À ce jour : **1.3.0 (4)**,
  déposée sur App Store Connect le 20 octobre 2026 ; l'Android 1.3.0 est sur Google Play.
- Le régime applicable, les exemptions éventuelles, et la question du transfert hors Union
  européenne.
- La cohérence avec la démarche américaine (BIS). La déclaration faite à Apple le
  20 octobre 2026 est `usesNonExemptEncryption = false`, c'est-à-dire que l'application
  n'emploie que de la cryptographie relevant des exemptions de la catégorie 5 partie 2.
  Cette réponse engage l'éditeur et doit être cohérente avec l'auto-classification BIS.
