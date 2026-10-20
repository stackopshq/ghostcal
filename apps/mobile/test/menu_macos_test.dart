import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// La barre de menus de macOS parle-t-elle la même langue que l'écran d'accueil ?
///
/// ─── Le défaut que ce test garde ───
///
/// Les items de menu natifs envoient un nom de méthode sur un canal, et `accueil.dart`
/// les reconnaît par ce nom. Rien ne relie les deux listes : ce sont deux chaînes de
/// caractères, dans deux langages, dans deux dossiers. Si l'une bouge — un item ajouté
/// en Swift, une casse renommée en Dart, une faute de frappe — le raccourci part, le
/// canal l'achemine, et **personne ne répond**. Aucune exception, aucun journal : la
/// touche ne fait simplement rien.
///
/// C'est arrivé. Le menu « Présentation » et le menu « Fichier » ont été construits et
/// posés sur la barre, avec leurs huit équivalents clavier, alors que le côté Dart ne
/// traitait que `reglages`. Sept raccourcis annoncés menaient dans le vide, et la barre
/// paraissait complète — c'est précisément la panne qu'un essai à la main ne remarque
/// pas si on n'essaie pas les huit.
///
/// ─── Pourquoi lire le source plutôt que monter l'écran ───
///
/// `EcranDAccueil` demande une session ouverte, un serveur et des clés déballées ; le
/// monter mesurerait surtout la qualité de ses bouchons. La propriété à tenir, elle, est
/// textuelle et se lit : **l'ensemble des méthodes émises par le natif est exactement
/// celui des méthodes traitées en Dart.**
void main() {
  final swift = File('macos/Runner/MenuDeLApplication.swift')
      .readAsStringSync();
  final dart = File('lib/ecrans/accueil.dart').readAsStringSync();

  /// Le corps du routeur, et lui seul : `accueil.dart` porte d'autres `switch` dont
  /// les casses n'ont rien à voir avec le menu.
  final routeur = dart.substring(dart.indexOf('_recevoirDuMenu'));

  Set<String> trouver(String source, RegExp motif) =>
      motif.allMatches(source).map((m) => m.group(1)!).toSet();

  test('chaque méthode émise par la barre de menus est traitée par l\'accueil', () {
    final emises = trouver(swift, RegExp(r'methode: "(\w+)"'));
    final traitees = {
      ...trouver(routeur, RegExp(r"case '(\w+)':")),
      // « Verrouiller » est traité avant le `switch`, pour passer même quand le reste
      // ne passe pas — voir le commentaire de `_recevoirDuMenu`.
      ...trouver(routeur, RegExp(r"appel\.method == '(\w+)'")),
    };

    // Le test porte sur les deux sens. Une méthode émise et non traitée est un
    // raccourci mort ; une casse Dart que rien n'émet est du code que rien n'atteint,
    // et le signe qu'un item a disparu du natif sans qu'on s'en aperçoive.
    expect(
      emises,
      isNotEmpty,
      reason: 'le parseur ne trouve plus rien dans le Swift',
    );
    expect(traitees, equals(emises));
  });

  test('chaque vue proposée par le menu est une vue que l\'agenda connaît', () {
    final emises = trouver(swift, RegExp(r'argument: "(\w+)"'));
    final traitees = trouver(routeur, RegExp(r"'(\w+)' => VueDAgenda\."));

    expect(
      emises,
      isNotEmpty,
      reason: 'le parseur ne trouve plus rien dans le Swift',
    );
    expect(traitees, equals(emises));
  });
}
