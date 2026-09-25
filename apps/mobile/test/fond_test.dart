import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Chaque écran peint-il son fond ?
///
/// ─── Le défaut que ce test garde ───
///
/// Le thème pose `scaffoldBackgroundColor: Colors.transparent`, délibérément : le fond
/// est un dégradé et un halo, peints par `FondGhost`, qu'un `Scaffold` opaque masquerait.
///
/// Les cinq onglets n'ont rien à faire : `EcranDAccueil` les enveloppe tous. Mais un
/// écran **poussé** sur la pile — `Navigator.push` — est frère de l'accueil dans la
/// pile, pas son enfant. Il n'hérite de rien. Son `Scaffold` transparent laisse voir le
/// noir du dessous.
///
/// Quatre écrans étaient dans ce cas au 25 septembre 2026 : création d'événement, profil,
/// sondages (deux écrans) et équipe. Dont l'écran de création, qui est le parcours
/// principal du produit.
///
/// ─── Pourquoi aucun test ne l'avait vu ───
///
/// Parce que le symptôme ne ressemble pas à la cause. En thème clair, les champs
/// restaient blancs sur noir et les libellés, en encre foncée, devenaient presque
/// illisibles. Cela se lit comme un thème sombre mal fichu, pas comme un fond absent. Un
/// test qui vérifie qu'un champ est présent, qu'un bouton réagit, qu'une valeur remonte,
/// passe intégralement : tout fonctionne, seule la peinture manque.
///
/// C'est une capture d'écran qui l'a montré — la deuxième du jeu App Store.
///
/// ─── Pourquoi ce test lit le source et ne monte pas les écrans ───
///
/// Monter chaque écran demanderait une session ouverte, un serveur, des clés déballées :
/// les écrans poussés n'existent qu'une fois le coffre ouvert. Un tel test mesurerait
/// surtout la qualité de ses propres bouchons.
///
/// La propriété à tenir est structurelle et se lit dans le source : **tout fichier qui
/// rend un `Scaffold` doit être soit enveloppé de `FondGhost`, soit logé dans un écran
/// qui l'est.** La seconde famille est nommée ci-dessous, et le test échoue si elle
/// change — ce qui est le moment de relire cette liste plutôt que de l'allonger sans y
/// penser.
void main() {
  final dossier = Directory('lib/ecrans');

  /// Les écrans logés dans `EcranDAccueil`, qui porte le `FondGhost` pour eux.
  ///
  /// Ce sont exactement les cinq destinations de la barre de navigation. En ajouter un
  /// ici sans qu'il y soit vraiment rouvrirait le défaut en silence : la liste est donc
  /// vérifiée contre `accueil.dart` par le second test.
  const heberges = {
    'agenda.dart',
    'taches.dart',
    'reunions.dart',
    'types_de_rendez_vous.dart',
    'reglages.dart',
  };

  test('tout écran qui rend un Scaffold peint son fond', () {
    // Trois issues, jamais deux : un dossier vide ne veut pas dire « rien à redire ».
    // C'est le cas où le test se croirait vert en n'ayant rien lu.
    expect(
      dossier.existsSync(),
      isTrue,
      reason: 'lib/ecrans introuvable — ce test ne mesure rien. Mauvais répertoire ?',
    );
    final fichiers = dossier.listSync().whereType<File>().where(
          (f) => f.path.endsWith('.dart'),
        );
    expect(
      fichiers.length,
      greaterThanOrEqualTo(10),
      reason: "Moins de dix écrans trouvés : le test n'a probablement rien lu.",
    );

    final fautifs = <String>[];
    for (final fichier in fichiers) {
      final nom = fichier.uri.pathSegments.last;
      if (heberges.contains(nom)) continue;
      final source = fichier.readAsStringSync();
      if (!source.contains('Scaffold(')) continue;
      if (!source.contains('FondGhost(')) fautifs.add(nom);
    }

    expect(
      fautifs,
      isEmpty,
      reason: 'Ces écrans rendent un Scaffold sans FondGhost, et le thème rend les '
          'Scaffold transparents : ils afficheront du noir. Enveloppez-les, ou '
          "ajoutez-les à `heberges` s'ils vivent à l'intérieur d'un écran qui porte "
          'déjà le fond.',
    );
  });

  test('la liste des écrans hébergés est celle des onglets de l\'accueil', () {
    final accueil = File('lib/ecrans/accueil.dart');
    expect(accueil.existsSync(), isTrue, reason: 'accueil.dart introuvable');
    final source = accueil.readAsStringSync();

    // `EcranDAgenda` → `agenda.dart` : la convention de nommage des imports suffit, et
    // se lit mieux qu'une analyse d'arbre syntaxique pour une propriété aussi simple.
    for (final nom in heberges) {
      expect(
        source.contains("import '$nom'"),
        isTrue,
        reason: "`$nom` est déclaré hébergé par l'accueil, mais accueil.dart ne "
            "l'importe pas. Soit il a déménagé et doit peindre son propre fond, soit "
            'la liste de `fond_test.dart` est périmée.',
      );
    }

    // `FondGhost` doit être dans l'accueil, sans quoi les cinq hébergés ne sont hébergés
    // par rien. C'est l'hypothèse sur laquelle repose tout le test précédent, et une
    // hypothèse non vérifiée est un endroit où un contrôle cesse de mesurer.
    expect(
      source.contains('FondGhost('),
      isTrue,
      reason: "accueil.dart ne porte plus de FondGhost : les cinq onglets n'ont plus de "
          'fond, et le premier test de ce fichier les laisse passer.',
    );
  });
}
