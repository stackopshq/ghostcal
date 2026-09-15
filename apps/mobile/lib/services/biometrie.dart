import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:local_auth/local_auth.dart';

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
enum Empreinte {
  visage(Icons.face, 'Face ID'),
  doigt(Icons.fingerprint, 'Touch ID'),
  autre(Icons.lock_outline, 'la biométrie');

  const Empreinte(this.icone, this.nom);
  final IconData icone;
  final String nom;
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
        _stockage = stockage ?? magasin;

  final LocalAuthentication _auth;
  final FlutterSecureStorage _stockage;

  static const _cle = 'ghostcal.phrase';

  /// Le magasin scellé. Constant et séparé de celui de [Trousseau] — voir l'en-tête.
  static const magasin = FlutterSecureStorage(
    iOptions: IOSOptions(
      accountName: 'ghostcal.biometrie',
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
      biometricPromptTitle: 'Ouvrir le coffre',
      biometricPromptSubtitle: 'GhostCal',
      biometricPromptNegativeButton: 'Utiliser la phrase',
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
  Future<void> retenir(String phrase) => _stockage.write(key: _cle, value: phrase);

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

  /// A-t-on une phrase scellée ? Ne déclenche **pas** la biométrie.
  ///
  /// `containsKey` interroge la présence, pas la valeur — sans quoi savoir s'il faut
  /// afficher le bouton demanderait le visage, et l'écran d'entrée ouvrirait une invite
  /// avant qu'on ait rien demandé.
  Future<bool> aUnePhrase() async {
    try {
      return await _stockage.containsKey(key: _cle);
    } on Object {
      return false;
    }
  }
}
