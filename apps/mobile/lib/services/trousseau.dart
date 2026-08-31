import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Ce qui survit à la fermeture de l'application.
///
/// **La phrase n'y figure pas, et n'y figurera pas.** Elle dérive la clé qui déballe la
/// clé privée de l'organisation ; l'enregistrer rendrait le chiffrement de bout en bout
/// décoratif — un attaquant qui obtient le trousseau obtiendrait le coffre avec.
///
/// Les jetons, eux, y vivent : ils rouvrent le compte, jamais le coffre. C'est la même
/// répartition que sur iOS natif, et c'est elle qui fait qu'au lancement l'application
/// demande la phrase seule.
///
/// `unlocked_this_device` reprend `kSecAttrAccessibleWhenUnlockedThisDeviceOnly` du
/// `Trousseau.swift` — accessible seulement écran déverrouillé, et jamais transféré vers
/// un autre appareil par une sauvegarde. Ce n'est pas un réglage par défaut : sans lui,
/// les jetons voyageraient dans l'iCloud Keychain.
class Trousseau {
  static const _stockage = FlutterSecureStorage(
    iOptions: IOSOptions(accessibility: KeychainAccessibility.unlocked_this_device),
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  static const serveur = 'ghostcal.serveur';
  static const email = 'ghostcal.email';
  static const jetonDAcces = 'ghostcal.jeton.acces';
  static const jetonDeRafraichissement = 'ghostcal.jeton.rafraichissement';

  static Future<String?> lire(String cle) => _stockage.read(key: cle);
  static Future<void> poser(String valeur, String cle) =>
      _stockage.write(key: cle, value: valeur);
  static Future<void> retirer(String cle) => _stockage.delete(key: cle);
}
