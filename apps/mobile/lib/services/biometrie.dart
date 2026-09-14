import 'package:flutter/material.dart';
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
  /// Rend `null` sur refus, sur échec, et sur entrée invalidée par un nouvel enrôlement.
  /// Les trois se ressemblent du point de vue de l'écran : on retombe sur la saisie.
  Future<String?> rappeler() async {
    try {
      return await _stockage.read(key: _cle);
    } on Object {
      return null;
    }
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
