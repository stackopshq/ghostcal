import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/biometrie.dart';
import 'package:ghostcal/services/trousseau.dart';

/// Ce que ces témoins gardent, et ce qu'ils ne peuvent pas garder.
///
/// Ils vérifient les **contraintes déclarées au magasin** — celles qui décident si la
/// phrase est scellée derrière le matériel ou simplement rangée. C'est vérifiable ici
/// parce que le paquet sérialise ses options ; la seule alternative serait un appareil
/// physique avec un visage enrôlé, et un désenrôlement au milieu du test.
///
/// Ce qu'ils **ne prouvent pas** : que l'appareil honore ces contraintes. Aucun test hors
/// matériel ne le peut. Sur Android, l'invalidation à l'enrôlement d'un nouveau visage
/// reste à confirmer sur le Redmi ; côté GhostPass, elle l'a été.
void main() {
  group('les contraintes du magasin biométrique', () {
    final android = Biometrie.magasin.aOptions.toMap();
    final apple = Biometrie.magasin.iOptions.params;

    /// Le témoin le plus important du fichier.
    ///
    /// Le défaut du paquet est `biometricOrDeviceCredential`, et il **désarme la
    /// garantie** : accepter le code de l'appareil rend `setInvalidatedByBiometricEnrollment`
    /// sans effet, puisqu'un visage nouvellement enrôlé n'invalide plus rien si le code
    /// suffit à ouvrir. C'est la correction qu'a dû recevoir l'ADR-0002 de GhostPass, et
    /// c'est exactement le genre de réglage qu'une montée de version reprend en silence.
    test('Android n\'accepte que la biométrie forte, jamais le code de l\'appareil', () {
      expect(android['biometricType'], 'strongBiometricOnly');
      expect(android['enforceBiometrics'], 'true');
    });

    /// `biometryAny` laisserait quelqu'un qui a le code ajouter son propre visage et
    /// ouvrir le coffre. `biometryCurrentSet` invalide l'entrée au nouvel enrôlement.
    test('Apple lie l\'entrée aux biométries actuellement enrôlées', () {
      expect(apple['accessControlFlags'], contains('biometryCurrentSet'));
      // `passcode` est `kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly` : pas de code
      // posé, pas d'entrée ; et jamais transférée vers un autre appareil.
      expect(apple['accessibility'], 'passcode');
    });

    /// Sans cloisonnement, la contrainte biométrique s'appliquerait aussi aux jetons de
    /// session : rouvrir l'application demanderait le visage pour lire une valeur qui n'a
    /// pas à être protégée ainsi, et le coffre deviendrait pénible sans être plus sûr.
    test('le magasin biométrique est séparé de celui des jetons', () {
      expect(android['storageNamespace'], isNotEmpty);
      expect(apple['accountName'], isNotNull);

      final jetons = Trousseau.magasin;
      expect(
        jetons.aOptions.toMap()['storageNamespace'],
        isNot(android['storageNamespace']),
        reason: 'les deux magasins partageraient leurs contraintes',
      );
      expect(
        jetons.iOptions.params['accessControlFlags'],
        isNull,
        reason: 'les jetons ne doivent jamais exiger le visage',
      );
    });

    /// La 11 met `resetOnError` à **vrai** par défaut : une simple erreur de lecture
    /// efface tout le magasin. Sur celui des jetons, cela déconnecte sans un mot ; ici,
    /// cela perdrait la phrase scellée sans que rien ne le dise.
    test('une erreur de lecture n\'efface pas le magasin', () {
      expect(android['resetOnError'], 'false');
      expect(Trousseau.magasin.aOptions.toMap()['resetOnError'], 'false');
    });
  });

  /// L'icône suit le matériel. Une icône Face ID en dur mentirait sur un téléphone à
  /// empreinte — c'est la raison d'être de cette énumération.
  test('chaque empreinte porte son propre dessin', () {
    final icones = Empreinte.values.map((e) => e.icone).toSet();
    expect(icones.length, Empreinte.values.length,
        reason: 'deux biométries différentes ne peuvent pas montrer le même dessin');
  });
}
