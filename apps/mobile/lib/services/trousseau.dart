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
  /// Public pour qu'un témoin puisse lire les contraintes réellement déclarées : deux
  /// magasins qui partageraient leurs options feraient exiger le visage pour lire un
  /// jeton, et rien à l'écran ne le dirait avant l'appareil.
  static const magasin = FlutterSecureStorage(
    iOptions: IOSOptions(accessibility: KeychainAccessibility.unlocked_this_device),
    // `resetOnError: false` **explicitement**, et ce n'est pas une redondance : la
    // version 9 le met à faux par défaut, la version 11 à **vrai**. La montée en 11,
    // faite le 2026-08-31 pour la biométrie, aurait donc retourné ce réglage en
    // silence — et sur une simple erreur de lecture il **efface tout le magasin**, or
    // les jetons de session y sont la seule copie existante. Aucune erreur, aucun
    // message : on se retrouve déconnecté sans cause visible.
    //
    // `encryptedSharedPreferences` a disparu en 11 : le stockage passe par un choix
    // d'algorithme, et `migrateOnAlgorithmChange` — vrai par défaut — reprend les
    // valeurs écrites par la 9. On ne le désactive pas : sans lui, les jetons d'une
    // installation existante deviendraient illisibles au premier lancement.
    aOptions: AndroidOptions(resetOnError: false),
  );

  static const serveur = 'ghostcal.serveur';
  static const email = 'ghostcal.email';
  static const jetonDAcces = 'ghostcal.jeton.acces';
  static const jetonDeRafraichissement = 'ghostcal.jeton.rafraichissement';

  static Future<String?> lire(String cle) => magasin.read(key: cle);
  static Future<void> poser(String valeur, String cle) =>
      magasin.write(key: cle, value: valeur);
  static Future<void> retirer(String cle) => magasin.delete(key: cle);
}
