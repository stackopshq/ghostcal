import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:local_auth/local_auth.dart';

import '../l10n/generated/app_localisations.dart';

/// Ouvrir le coffre par le visage ou l'empreinte.
///
/// ─── Ce que ce fichier contredit, et pourquoi ───
///
/// `Trousseau` porte, écrit noir sur blanc : « la phrase n'y figure pas, et n'y figurera
/// pas ». Cette phrase reste vraie **pour le trousseau des jetons**, et elle l'est pour la
/// raison qui y est donnée : sous l'accessibilité ordinaire, un attaquant qui obtient le
/// magasin obtiendrait la phrase, donc le coffre, et le chiffrement de bout en bout
/// deviendrait décoratif.
///
/// Ce magasin-ci n'est pas celui-là. La phrase y est scellée sous une contrainte
/// matérielle : côté Apple, `kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly` avec
/// `.biometryCurrentSet` ; côté Android, une clé du KeyStore qui exige une authentification
/// de l'utilisateur. Copier le fichier ne suffit plus — il faut le visage, sur cet
/// appareil, à cet instant. C'est exactement ce que fait GhostPass iOS dans
/// `Keychain.swift`, et l'ADR-0002 pour Android.
///
/// ─── Deux pièges, et ce qu'on en fait ───
///
/// **`AndroidBiometricType.biometricOrDeviceCredential` est le défaut du paquet**, et il
/// désarme la garantie : accepter le code de l'appareil rend `setInvalidatedByBiometricEnrollment`
/// sans effet, puisqu'un nouveau visage enrôlé n'invalide plus rien si le code suffit.
/// C'est la correction qu'a dû recevoir l'ADR-0002 de GhostPass. On passe donc
/// `strongBiometricOnly` **explicitement**, et un témoin vérifie que le défaut n'a pas été
/// repris en silence.
///
/// **Le magasin est cloisonné** — `accountName` côté Apple, `storageNamespace` côté
/// Android. Sans cela, la contrainte biométrique s'appliquerait aussi aux jetons de
/// session, et le simple fait de rouvrir l'application demanderait le visage pour lire une
/// valeur qui n'a pas à être protégée ainsi.
///
/// ─── Ce que `local_auth` fait ici, et ne fait pas ───
///
/// Il sert **uniquement** à savoir si l'appareil a une biométrie utilisable, et laquelle,
/// pour décider d'afficher le bouton et quelle icône y mettre. Il **n'est pas** la barrière
/// de sécurité : celle-ci est dans le KeyStore et le trousseau, et elle tient même si
/// quelqu'un contourne l'appel Dart. Une biométrie qui ne serait qu'un `local_auth` devant
/// une valeur lisible par n'importe quoi d'autre ressemblerait à GhostPass à l'écran sans
/// en avoir la garantie.
///
/// ─── Et la garantie, constatée sur matériel ───
///
/// Le 2026-09-26, sur un iPhone 17 Pro, dans la même exécution :
///
///     entrée sans contrôle d'accès      lecture en      4 ms
///     entrée sous biometryCurrentSet    lecture en 45 174 ms, après Face ID
///
/// Trois ordres de grandeur. La porte existe, et le trousseau la fait franchir — ce
/// n'était jusque-là qu'une option déclarée, et une option déclarée qu'une plateforme
/// ignore ne produit aucune erreur. Le relevé vit dans
/// `integration_test/biometrie_trois_etats_test.dart`, qui le refait à chaque exécution
/// plutôt que de le croire sur parole.
enum Empreinte {
  visage(Icons.face),
  doigt(Icons.fingerprint),
  autre(Icons.lock_outline);

  const Empreinte(this.icone);
  final IconData icone;

  /// Le nom du geste, dans la langue de l'écran.
  ///
  /// « Face ID » et « Touch ID » sont des noms de produits d'Apple : ils ne se traduisent
  /// pas, et sont rendus tels quels. Le repli générique, lui, **se traduit** — c'est une
  /// erreur que GhostPass iOS a faite puis corrigée : un `nom` français en dur donnait
  /// « Open with la biométrie » sur une interface anglaise, à l'endroit précis où le
  /// produit demande qu'on lui fasse confiance.
  ///
  /// Le `switch` reste collé aux valeurs parce qu'il est **exhaustif** : ajouter une
  /// biométrie sans lui donner de nom ne compile pas. Une table posée ailleurs laisserait
  /// passer l'oubli, et l'écran afficherait un vide. Même motif que
  /// `DelaiDeVerrouillage.libelle`.
  String nom(L l) => switch (this) {
        Empreinte.visage => 'Face ID',
        Empreinte.doigt => 'Touch ID',
        Empreinte.autre => l.laBiometrie,
      };
}

/// Les trois libellés de l'invite biométrique **d'Android**.
///
/// iOS prend les siens ailleurs — `NSFaceIDUsageDescription`, localisé par
/// `InfoPlist.strings` — parce que c'est le système qui compose l'alerte. Android, lui,
/// veut les chaînes au moment de l'appel : elles doivent donc traverser depuis un écran
/// qui a un `BuildContext`, sans quoi elles restent en dur dans la langue de celle qui a
/// écrit le code. C'est exactement le défaut relevé le 2026-09-25 sur GhostPass Android.
///
/// [repli] nomme **le chemin long, pas un abandon** : « Utiliser la phrase » et non
/// « Annuler ». Le geste refusé renvoie au clavier, et l'écrire évite de laisser croire
/// qu'on est coincé — GhostPass y met « Mot de passe maître » pour la même raison.
class InvitesBiometriques {
  const InvitesBiometriques({
    required this.titre,
    required this.sousTitre,
    required this.repli,
  });

  /// Les libellés tirés des traductions de l'application.
  factory InvitesBiometriques.depuis(L l) => InvitesBiometriques(
        titre: l.ouvrirLeCoffre,
        // Le nom du produit, verbatim : il ne se traduit pas.
        sousTitre: 'GhostCal',
        repli: l.utiliserLaPhrase,
      );

  final String titre;
  final String sousTitre;
  final String repli;
}

/// Ce qu'a répondu le magasin scellé.
///
/// **Ces cas ne sont pas une commodité : c'est la leçon de GhostPass iOS.** Là-bas, le
/// déclenchement automatique de la biométrie a coûté trois correctifs faux, tous fondés
/// sur la même confusion — un garde « une seule demande par présentation » qui se
/// refermait sur une question **jamais posée**. Tant que l'écran ne reçoit qu'un `null`,
/// il ne peut pas faire la différence entre « elle a dit non » et « on n'a pas pu lui
/// demander », et il n'a alors le choix qu'entre harceler et rester muet.
enum Issue {
  /// La phrase est là.
  ouverte,

  /// La question a été posée, et le visage n'a pas ouvert — refus, ou non-reconnaissance.
  /// C'est un choix ou un échec de l'utilisateur, pas une panne : on ne dit rien de plus
  /// que ce que le système vient déjà d'afficher.
  refusee,

  /// La question n'a **pas pu être posée**. Le trousseau répond `interactionNotAllowed`
  /// tant que l'application n'est pas au premier plan — l'état exact d'un premier
  /// affichage au lancement. Ce n'est pas un refus, et les confondre fabrique soit un
  /// bouton mort, soit une invite en rafale.
  pasMaintenant,

  /// Rien n'est scellé. C'est aussi ce que rend Apple après un nouvel enrôlement : sous
  /// `biometryCurrentSet`, le système **supprime** l'entrée plutôt que de la refuser.
  absente,

  /// L'entrée a été invalidée par un nouvel enrôlement — chemin Android, où la clé
  /// survit à l'invalidation et se signale par `KeyPermanentlyInvalidatedException`.
  /// C'est la garantie qui joue, pas un défaut : il faut retaper la phrase et la resceller.
  invalidee,

  /// Autre chose. On ne devine pas : l'écran montrera le détail tel quel, plutôt que de
  /// le ranger dans une case qui ferait passer une panne pour un refus.
  echec,
}

/// La réponse du magasin : une issue, et la phrase quand il y en a une.
class Rappel {
  const Rappel(this.issue, {this.phrase, this.detail});

  final Issue issue;
  final String? phrase;

  /// Ce que la plateforme a dit, quand elle a dit quelque chose qu'on n'a pas su classer.
  /// Montré à l'écran : une panne qu'on ne nomme pas est une panne qu'on ne corrigera pas.
  final String? detail;
}

class Biometrie {
  Biometrie({LocalAuthentication? auth, FlutterSecureStorage? stockage})
      : _auth = auth ?? LocalAuthentication(),
        _injecte = stockage;

  final LocalAuthentication _auth;

  /// Le magasin imposé par un témoin, quand il y en a un. Il l'emporte toujours : un test
  /// ne doit jamais se retrouver avec un vrai trousseau sous la main.
  final FlutterSecureStorage? _injecte;

  InvitesBiometriques? _invites;

  /// Les libellés de l'invite Android, posés par l'écran qui a le contexte.
  ///
  /// C'est un point mouvant parce que la langue l'est : l'application suit le réglage de
  /// l'appareil, et celui-ci peut changer pendant qu'elle vit. Un magasin figé à la
  /// construction porterait la langue du premier lancement.
  set invites(InvitesBiometriques valeur) => _invites = valeur;

  static const _cle = 'ghostcal.phrase';

  /// `kSecUseAuthenticationUIFail`, par sa valeur littérale.
  ///
  /// Le paquet passe cette option **telle quelle** au dictionnaire de requête, sans la
  /// traduire depuis un nom symbolique : il faut donc lui donner la chaîne que
  /// `Security.framework` porte réellement. Relevée le 2026-09-26, pas recopiée d'une
  /// documentation :
  ///
  ///     kSecUseAuthenticationUIAllow  u_AuthUIA
  ///     kSecUseAuthenticationUIFail   u_AuthUIF
  ///     kSecUseAuthenticationUISkip   u_AuthUIS
  ///
  /// Une faute de frappe ici ne casse rien à la compilation et ramène simplement l'invite.
  /// C'est ce que mesure le témoin d'intégration.
  static const _sansInvite = 'u_AuthUIF';

  FlutterSecureStorage get _stockage => _injecte ?? magasin(_invites);

  /// Le même magasin, mais **interdit de présenter quoi que ce soit**.
  ///
  /// Sert uniquement à l'interrogation de présence. Voir [sceau] pour ce que ça change.
  FlutterSecureStorage get _stockageMuet =>
      _injecte ?? magasin(_invites, true);

  /// Le magasin scellé, séparé de celui de [Trousseau] — voir l'en-tête.
  ///
  /// Ce n'est plus une constante, et la raison est de langue, pas de technique : les trois
  /// libellés de l'invite Android viennent des traductions, donc d'un `BuildContext`, donc
  /// pas d'un `const`. Les **contraintes**, elles, ne dépendent de rien et restent
  /// identiques d'un appel à l'autre — c'est ce que garde `biometrie_test.dart`.
  ///
  /// [invites] nul laisse au paquet son libellé par défaut plutôt que de poser le nôtre en
  /// français : un texte générique anglais se reconnaît comme tel, du français servi à un
  /// anglophone se lit comme un produit cassé. Le cas ne se produit qu'avant qu'un écran
  /// ait posé les siens.
  /// [muet] interdit à Apple de présenter une invite : la requête échoue plutôt que de
  /// demander un visage. C'est ce qui rend l'interrogation de présence honnête — voir
  /// [sceau]. Sans effet sur Android, dont le KeyStore ne demande rien pour une question
  /// de présence.
  static FlutterSecureStorage magasin(
    [InvitesBiometriques? invites, bool muet = false]
  ) =>
      FlutterSecureStorage(
    iOptions: IOSOptions(
      accountName: 'ghostcal.biometrie',
      authenticationUIBehavior: muet ? _sansInvite : null,
      // `passcode` est `kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly` : l'entrée
      // n'existe que si un code est posé, ne quitte jamais l'appareil, et disparaît si le
      // code est retiré. Le même choix que `Keychain.swift`.
      accessibility: KeychainAccessibility.passcode,
      // `biometryCurrentSet` et non `biometryAny` : enrôler un nouveau visage invalide
      // l'entrée. Sans cela, quelqu'un qui obtient le code de l'appareil ajoute son
      // propre visage et ouvre le coffre.
      accessControlFlags: [AccessControlFlag.biometryCurrentSet],
    ),
    aOptions: AndroidOptions.biometric(
      enforceBiometrics: true,
      biometricType: AndroidBiometricType.strongBiometricOnly,
      resetOnError: false,
      storageNamespace: 'ghostcal.biometrie',
      biometricPromptTitle: invites?.titre,
      biometricPromptSubtitle: invites?.sousTitre,
      biometricPromptNegativeButton: invites?.repli,
    ),
  );

  /// La biométrie utilisable sur cet appareil, ou `null` s'il n'y en a pas.
  ///
  /// Rend `null` aussi quand le matériel existe mais que rien n'est enrôlé : proposer un
  /// bouton qui ouvrira une boîte d'erreur est pire que ne rien proposer.
  Future<Empreinte?> disponible() async {
    try {
      if (!await _auth.canCheckBiometrics) return null;
      final types = await _auth.getAvailableBiometrics();
      if (types.isEmpty) return null;
      if (types.contains(BiometricType.face)) return Empreinte.visage;
      if (types.contains(BiometricType.fingerprint)) return Empreinte.doigt;
      return Empreinte.autre;
    } on Object {
      // Un appareil qui refuse de répondre est traité comme un appareil sans biométrie.
      return null;
    }
  }

  /// Scelle la phrase. À n'appeler qu'après un déverrouillage réussi : on n'enregistre
  /// jamais une phrase qu'on n'a pas vue fonctionner.
  ///
  /// Rend `true` si le sceau est posé. **Ne jette pas** : constaté sur émulateur, un
  /// magasin dont la clé est morte fait échouer l'écriture par une exception non
  /// rattrapée. Or cet appel a lieu *après* un déverrouillage réussi — laisser filer
  /// l'exception ferait échouer une ouverture de coffre qui, elle, a parfaitement marché,
  /// et pour une commodité dont personne n'avait besoin à cet instant.
  Future<bool> retenir(String phrase) async {
    try {
      await _stockage.write(key: _cle, value: phrase);
      return true;
    } on Object {
      return false;
    }
  }

  /// Redemande la phrase — c'est cet appel qui déclenche le visage ou l'empreinte.
  ///
  /// Ne rend jamais un `null` nu : voir [Issue]. Le coût de les confondre n'est pas
  /// théorique, il est écrit dans l'historique de GhostPass.
  Future<Rappel> rappeler() async {
    try {
      final phrase = await _stockage.read(key: _cle);
      return phrase == null
          ? const Rappel(Issue.absente)
          : Rappel(Issue.ouverte, phrase: phrase);
    } on PlatformException catch (e) {
      return _classer(e);
    } on Object catch (e) {
      return Rappel(Issue.echec, detail: '$e');
    }
  }

  /// Range la panne de la plateforme dans une des [Issue].
  ///
  /// ─── Pourquoi les deux côtés ne se lisent pas pareil ───
  ///
  /// Apple rend un `OSStatus` **numérique** dans `details` : c'est un code stable,
  /// documenté, et le classer est sûr.
  ///
  /// Android, lui, emballe tout dans `code: "Exception encountered"` avec la trace en
  /// texte. Reconnaître le nom de la classe dans cette trace est un instrument faible, et
  /// il faut le dire plutôt que d'en tirer une fausse assurance : une montée de version du
  /// paquet peut changer ce texte sans rien casser à la compilation. C'est pourquoi ce qui
  /// n'est pas reconnu tombe dans [Issue.echec] — **jamais** dans [Issue.refusee]. Ranger
  /// l'inconnu parmi les refus rendrait l'écran muet devant une vraie panne, ce qui est
  /// précisément le défaut que ce fichier cherche à ne pas reproduire.
  /// Le classement, ouvert aux témoins.
  ///
  /// Exposé parce que c'est la seule pièce du fichier qu'un test peut réellement éprouver :
  /// le reste demande un trousseau, donc un appareil. La règle qu'il garde — l'inconnu ne
  /// devient jamais un refus — est aussi celle qui se perdrait le plus discrètement.
  @visibleForTesting
  static Issue classerPourTemoin(PlatformException e) => _classer(e).issue;

  static Rappel _classer(PlatformException e) {
    // ─── Apple : le code numérique fait foi ───
    final statut = e.details;
    if (statut is int) {
      switch (statut) {
        // errSecUserCanceled (-128) : elle a écarté l'invite.
        // errSecAuthFailed (-25293) : le visage n'a pas été reconnu.
        // Dans les deux cas la question a bien été posée.
        case -128:
        case -25293:
          return const Rappel(Issue.refusee);
        // errSecInteractionNotAllowed (-25308) : le trousseau n'était pas en état de
        // présenter quoi que ce soit. La question n'a pas été posée.
        case -25308:
          return const Rappel(Issue.pasMaintenant);
        // errSecItemNotFound (-25300) : plus rien de scellé — le cas d'un nouvel
        // enrôlement sous `biometryCurrentSet`, l'entrée ayant été supprimée.
        case -25300:
          return const Rappel(Issue.absente);
      }
    }

    // ─── Android : on reconnaît le nom de la classe, ou on avoue ───
    final trace = '${e.code} ${e.message} ${e.details}';
    if (trace.contains('KeyPermanentlyInvalidatedException')) {
      return const Rappel(Issue.invalidee);
    }
    // ─── Ce que le paquet perd en chemin, et qu'il faut rattraper au texte ───
    //
    // Mesuré sur émulateur, après enrôlement d'une empreinte de plus : le KeyStore lève
    // bien `KeyPermanentlyInvalidatedException` — on le lit dans `logcat` — mais
    // `flutter_secure_storage` 11 l'attrape, la remplace par une `java.lang.Exception`
    // de son cru, et **la cause n'atteint jamais Dart**. Vérifié plutôt que supposé :
    // `details` fait 2073 octets et ne contient nulle part le nom de la classe.
    //
    // Il ne reste que le message du paquet. C'est un instrument faible, et il faut le
    // dire : une montée de version peut le reformuler sans rien casser à la compilation.
    // Il est retenu quand même parce que le cas contraire — ranger une clé morte dans
    // « panne inconnue » — laisse l'écran afficher une trace Java à quelqu'un qui voulait
    // seulement ouvrir son agenda.
    //
    // Les deux formulations connues mènent à la même conduite : le sceau est illisible,
    // il faut le refaire. Le message affiché est donc écrit pour couvrir les deux causes
    // sans en affirmer une qu'on ne peut pas distinguer.
    if (trace.contains('Migration failed after algorithm change') ||
        trace.contains('key type incompatible with cipher')) {
      return const Rappel(Issue.invalidee);
    }
    if (trace.contains('UserNotAuthenticatedException') ||
        trace.contains('BIOMETRIC_ERROR_NONE_ENROLLED')) {
      return const Rappel(Issue.invalidee);
    }
    // L'utilisateur a écarté l'invite biométrique.
    if (trace.contains('ERROR_USER_CANCELED') ||
        trace.contains('ERROR_NEGATIVE_BUTTON') ||
        trace.contains('ERROR_CANCELED')) {
      return const Rappel(Issue.refusee);
    }
    return Rappel(Issue.echec, detail: e.message ?? e.code);
  }

  /// Oublie la phrase. Appelé quand on coupe le réglage et à la déconnexion — verrouiller
  /// le coffre, en revanche, ne l'efface pas : c'est précisément le cas où l'on veut
  /// rouvrir par le visage.
  Future<void> oublier() async {
    try {
      await _stockage.delete(key: _cle);
    } on Object {
      // Rien à dire : l'entrée est absente ou illisible, le résultat voulu est le même.
    }
  }

  /// L'état du sceau, **sans** déclencher la biométrie.
  ///
  /// Savoir s'il faut afficher le bouton ne doit pas coûter un visage : l'écran d'entrée
  /// et celui des réglages posent cette question à leur ouverture, avant qu'on ait rien
  /// demandé.
  ///
  /// Deux précautions, et il en fallait **deux** :
  ///
  /// - `containsKey` interroge la présence et non la valeur ;
  /// - et la requête part sous `kSecUseAuthenticationUIFail`, sans quoi Apple présente
  ///   l'invite quand même. La première seule ne suffisait pas — voir plus bas, c'est
  ///   mesuré.
  ///
  /// ─── Pourquoi ceci ne rend plus un simple `bool` ───
  ///
  /// Mesuré sur émulateur Android, après avoir enrôlé une empreinte de plus : le KeyStore
  /// lève `KeyPermanentlyInvalidatedException` **dès `containsKey`**, avant toute lecture.
  /// L'ancien `catch` rendait alors `false`, exactement comme « rien n'a jamais été
  /// scellé ». Conséquence : le bouton disparaissait sans un mot, le déclenchement
  /// automatique ne partait pas, et le message d'invalidation — écrit pour ce cas précis —
  /// ne pouvait jamais s'afficher. La garantie fonctionnait, et le produit la taisait.
  ///
  /// Rend :
  /// - [Issue.ouverte]   — une phrase est scellée et la clé est vivante ;
  /// - [Issue.absente]   — rien de scellé (dont le cas Apple, où l'entrée est supprimée) ;
  /// - [Issue.invalidee] — la clé est morte avec l'enrôlement qui l'a créée ;
  /// - [Issue.echec]     — le magasin n'a pas répondu, et on ne devine pas.
  Future<Issue> sceau() async {
    try {
      final present = await _stockageMuet.containsKey(key: _cle);
      return present ? Issue.ouverte : Issue.absente;
    } on PlatformException catch (e) {
      final issue = _classer(e).issue;
      // ─── Le renversement, et il est mesuré ───
      //
      // Sous `kSecUseAuthenticationUIFail`, `errSecInteractionNotAllowed` **ne veut plus
      // dire** « on ne peut pas demander maintenant ». Il veut dire : *l'entrée est là,
      // elle est gardée, et on a interdit qu'on la demande*. C'est-à-dire exactement la
      // réponse cherchée — un sceau posé et vivant — obtenue sans réveiller personne.
      //
      // Sans le drapeau, la même question **présente Face ID**. Mesuré le 2026-09-26 sur
      // iPhone 17 Pro : 29 425 ms pour cette interrogation de présence, contre 0 ms pour
      // la même sur une entrée sans contrôle d'accès. Le commentaire précédent affirmait
      // que « `containsKey` ne présente rien » ; c'était faux, et rien ne pouvait le dire
      // — les témoins hors matériel emploient un magasin feint, et le simulateur n'applique
      // pas du tout le contrôle d'accès, donc y répondait en 0 ms.
      //
      // Conséquence du défaut, tant qu'il a duré : ouvrir les réglages demandait un visage
      // pour afficher une ligne d'état, et l'écran d'entrée le demandait **deux fois**.
      // Une invite qu'on n'a pas demandée est une invite qu'on apprend à écarter.
      return issue == Issue.pasMaintenant ? Issue.ouverte : issue;
    } on Object {
      return Issue.echec;
    }
  }
}
