// Le cœur commun, vu depuis Dart.
//
// Ce fichier ne teste pas la cryptographie : elle est éprouvée dans le cœur Rust, et le
// serait deux fois pour rien. Il teste **la frontière** — qu'un appel la traverse et
// revienne juste. Sans lui, une chaîne de construction cassée se manifesterait au premier
// déverrouillage d'un utilisateur, pas à la compilation.
//
// C'est un test d'intégration et non un test unitaire : il lui faut la bibliothèque
// native, donc un appareil ou un simulateur. Un `flutter test` ordinaire ne chargerait
// rien et passerait au vert sans avoir traversé quoi que ce soit — précisément le genre
// de contrôle rassurant qu'on cherche à éviter.

import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/src/rust/api/coeur.dart';
import 'package:ghostcal/src/rust/frb_generated.dart';
import 'package:integration_test/integration_test.dart';

String enHexa(Uint8List octets) =>
    octets.map((o) => o.toRadixString(16).padLeft(2, '0')).join();

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async => await RustLib.init());

  test('la dérivation traverse la frontière et rend ce que le navigateur rend', () async {
    // Le vecteur vient de `hash-wasm`, la bibliothèque Argon2 du navigateur, et non du
    // cœur. C'est ce qui le rend utile : il vérifie que Dart obtient ce que le web
    // obtient, et non que le cœur est cohérent avec lui-même.
    //
    // Valeur identique à celle du test Swift `CoeurTests.testLaDerivationTraverseLaFrontiere`,
    // reprise caractère par caractère. Si elle changeait en traduisant, ce serait un
    // défaut et non une adaptation.
    final sel = Uint8List.fromList(List.filled(16, 7));
    final cle = await deriverCle(phrase: 'correct horse', sel: sel);
    expect(
      enHexa(cle),
      '7b985d8fa00c9eccccf918c8cb9feaa8036af381caf6f498e099b5b849b8c18a',
      reason: 'la clé dérivée diffère de celle du navigateur : ce que le web a scellé '
          'ne s\'ouvrirait pas ici',
    );
  });

  test('un sceau fait l\'aller-retour', () async {
    final paire = await genererPaire();
    final scelle = await scellerVers(
      publique: paire.publique,
      clair: Uint8List.fromList(utf8.encode('rendez-vous')),
      domaine: 'ghostcal-zk-v1',
    );
    final ouvert = await ouvrirSceau(
      privee: paire.privee,
      blob: scelle,
      domaine: 'ghostcal-zk-v1',
    );
    expect(utf8.decode(ouvert), 'rendez-vous');
  });

  test('le domaine sépare les produits', () async {
    // Un seul cœur sert ghostcal et ghostmail ; c'est le domaine qui les empêche de lire
    // les données l'un de l'autre. Si cette séparation cédait, elle céderait en silence.
    final paire = await genererPaire();
    final scelle = await scellerVers(
      publique: paire.publique,
      clair: Uint8List.fromList(utf8.encode('agenda')),
      domaine: 'ghostcal-zk-v1',
    );
    await expectLater(
      ouvrirSceau(privee: paire.privee, blob: scelle, domaine: 'ghostmail-zk-v1'),
      throwsA(anything),
      reason: 'un autre produit ne doit pas ouvrir ce sceau',
    );
  });

  test('la taille du sel est imposée', () async {
    // Le sel fait 16 octets côté web. En accepter d'autres produirait des clés que le
    // navigateur ne saurait pas reproduire.
    await expectLater(
      deriverCle(phrase: 'x', sel: Uint8List.fromList(List.filled(8, 0))),
      throwsA(anything),
    );
  });
}
