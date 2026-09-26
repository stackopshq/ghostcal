import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Où reste-t-il du français en dur, et combien ?
///
/// ─── Pourquoi ce test plutôt qu'une note dans un fichier ───
///
/// La traduction FR/EN est faite pour tout ce que l'utilisateur voit à l'écran. Il reste
/// une poignée de messages produits **au fond des services**, qui n'ont pas de
/// `BuildContext` et ne peuvent donc pas appeler `L.of(context)`. Les corriger demande de
/// leur faire rendre un code d'erreur que l'écran traduirait — un chantier d'architecture,
/// pas un remplacement de chaîne.
///
/// Écrire « il reste quelques chaînes » dans une documentation vieillit mal : personne ne
/// sait plus lesquelles, ni si le nombre monte. Ce test les **nomme**. Il échoue si une
/// nouvelle apparaît, et il échoue aussi si l'une disparaît — auquel cas la liste ci-dessous
/// est à raccourcir, ce qui est exactement le moment de le faire.
///
/// ─── Ce qu'il ne prouve pas ───
///
/// Qu'une traduction est **bonne**. Il mesure l'absence de français en dur, pas la justesse
/// de l'anglais. Celle-là se relit.
void main() {
  /// Un mot français : soit un accent, soit un mot outil qui n'existe pas en anglais.
  ///
  /// « Face ID » et « Touch ID » ne déclenchent rien, et c'est voulu : ce sont des noms
  /// de produits d'Apple, qui ne se traduisent pas.
  final motFrancais = RegExp(
    r'[àâäéèêëîïôöùûüçœÀÂÉÈÊÎÔÙÇ]|'
    r'\b(?:le|la|les|un|une|des|du|de|et|ou|est|sont|pas|pour|sur|avec|dans|'
    r'vous|votre|vos|ce|cette|aucun|aucune|qui|que|se|sans)\b',
    caseSensitive: false,
  );
  final litteral = RegExp(r"'((?:[^'\\\n]|\\.){2,300})'" r'|"((?:[^"\\\n]|\\.){2,300})"');

  /// Ce qui reste, nommé fichier par fichier. Chaque entrée est un message d'erreur ou un
  /// libellé d'énumération produit sans contexte.
  ///
  /// Le chemin pour les supprimer : que le service rende une **valeur** — un code, une
  /// énumération — et que l'écran, qui a un contexte, la traduise. C'est ce qui a été fait
  /// pour `DelaiDeVerrouillage.libelle(L)` et `Membre.roleLisible(L)`.
  ///
  /// `lib/services/biometrie.dart` **en est sorti** le 2026-09-26, et c'est le chemin
  /// décrit ci-dessus qui l'en a sorti : le fichier portait « la biométrie » et les deux
  /// libellés de l'invite Android, tous trois dans un `static const` que le
  /// `BiometricPrompt` affichait tels quels à un anglophone. Le service rend désormais une
  /// **valeur** — l'énumération `Empreinte`, et `InvitesBiometriques` — que l'écran
  /// traduit. Les deux clés de l'invite existaient déjà dans les `.arb` depuis un passage
  /// précédent : elles avaient été traduites, puis jamais branchées, et rien ne le disait.
  const restant = <String, int>{
    'lib/services/api.dart': 1, // « Le serveur a répondu {code}. »
    'lib/services/auth.dart': 2, // phrase incorrecte, coffre fermé
    'lib/services/session.dart': 2, // adresse invalide, session expirée
  };

  /// Les fichiers qu'on n'examine pas, et pourquoi.
  bool exclu(String chemin) =>
      // Bindings produits par flutter_rust_bridge : ils ne nous appartiennent pas.
      chemin.contains('/src/rust/') ||
      // Code produit par `flutter gen-l10n` : c'est la **sortie** de la traduction. L'y
      // chercher du français reviendrait à faire rougir le contrôle sur sa propre réussite.
      chemin.contains('/l10n/generated/');

  Map<String, List<String>> releve() {
    final trouves = <String, List<String>>{};
    final fichiers = Directory('lib')
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart') && !exclu(f.path));
    for (final fichier in fichiers) {
      final lignes = fichier.readAsLinesSync();
      for (final ligne in lignes) {
        final nu = ligne.trim();
        // Les commentaires sont en français et doivent le rester : ils s'adressent à
        // l'équipe, pas à l'utilisateur. Les compter ferait rougir tous les fichiers.
        if (nu.startsWith('//') || nu.startsWith('import ')) continue;
        for (final m in litteral.allMatches(ligne)) {
          final texte = m.group(1) ?? m.group(2);
          if (texte != null && motFrancais.hasMatch(texte)) {
            (trouves[fichier.path] ??= []).add(texte);
          }
        }
      }
    }
    return trouves;
  }

  test("le relevé lit bien quelque chose", () {
    // Trois issues, jamais deux : si `lib/` n'était pas là, tous les contrôles suivants
    // seraient verts sans avoir rien lu. C'est le vert le plus dangereux qui soit.
    expect(Directory('lib').existsSync(), isTrue,
        reason: 'lib/ introuvable — ce test ne mesure rien. Mauvais répertoire de travail ?');
    final dart = Directory('lib')
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'));
    expect(dart.length, greaterThan(20),
        reason: "Moins de vingt fichiers Dart : le relevé n'a probablement rien parcouru.");
  });

  test('aucun texte français en dur dans les écrans', () {
    final trouves = releve()
      ..removeWhere((chemin, _) => !chemin.startsWith('lib/ecrans'));
    expect(
      trouves,
      isEmpty,
      reason: 'Ces écrans portent encore du français en dur. Ajoutez la clé dans '
          'lib/l10n/app_fr.arb et app_en.arb, relancez `flutter gen-l10n`, et '
          'remplacez le littéral par L.of(context).<clé>.',
    );
  });

  test('ce qui reste dans les services est exactement ce qui est déclaré', () {
    final trouves = releve()
      ..removeWhere((chemin, _) => chemin.startsWith('lib/ecrans'));
    final compte = {for (final e in trouves.entries) e.key: e.value.length};

    // On compare les deux sens. Un fichier apparu est une régression ; un fichier disparu
    // veut dire que le chantier a avancé et que cette liste est périmée — les deux
    // méritent qu'on s'arrête, et une liste qu'on ne réduit jamais finit par être fausse.
    expect(
      compte,
      restant,
      reason: 'Le français en dur hors des écrans a changé.\n'
          'Plus qu\'attendu : une régression — traduisez.\n'
          'Moins qu\'attendu : le chantier a avancé — raccourcissez `restant` '
          'dans ce fichier.\n'
          'Relevé : ${trouves.map((k, v) => MapEntry(k, v))}',
    );
  });
}
