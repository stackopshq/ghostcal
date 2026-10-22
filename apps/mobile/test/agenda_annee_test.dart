import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/ecrans/agenda_annee.dart';
import 'package:ghostcal/l10n/generated/app_localisations.dart';
import 'package:ghostcal/theme.dart';

/// La vue Année.
///
/// ─── Ce que ces témoins gardent ───
///
/// Une grille dense est l'endroit où les débordements se cachent : douze mois, chacun
/// sept colonnes et six rangées, dans une fenêtre dont on ne choisit pas la taille. Le
/// mois et la semaine ont déjà débordé deux fois dans ce projet, de 6,3 et de 11 points,
/// et dans les deux cas le témoin existant passait — parce qu'un débordement de rendu
/// n'est **pas** une exception levée. Il faut le demander à `takeException`.
void main() {
  Widget sous(Widget enfant, {Locale langue = const Locale('fr')}) =>
      MaterialApp(
        locale: langue,
        localizationsDelegates: const [
          ...L.localizationsDelegates,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
        ],
        supportedLocales: L.supportedLocales,
        theme: themeGhostcal(Brightness.light),
        home: Scaffold(body: enfant),
      );

  Widget annee({DateTime? sur, ValueChanged<DateTime>? surJour}) =>
      GrilleDeLAnnee(
        annee: sur ?? DateTime(2026, 6, 15),
        premierJour: 1,
        surJour: surJour ?? (_) {},
      );

  testWidgets('les douze mois sont là, nommés dans la langue', (tester) async {
    // Une fenêtre où les douze mois tiennent : `GridView` ne construit que ce qui est
    // visible, et un témoin qui cherche « Décembre » dans 800 × 600 ne mesure que la
    // paresse de la grille.
    tester.view.physicalSize = const Size(1440 * 2, 1000 * 2);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(sous(annee()));
    await tester.pumpAndSettle();
    for (final nom in [
      'Janvier',
      'Février',
      'Mars',
      'Avril',
      'Mai',
      'Juin',
      'Juillet',
      'Août',
      'Septembre',
      'Octobre',
      'Novembre',
      'Décembre',
    ]) {
      expect(
        find.text(nom),
        findsOneWidget,
        reason: '$nom manque à la grille de l\'année',
      );
    }
  });

  testWidgets('en anglais aussi', (tester) async {
    // Une fenêtre où les douze mois tiennent : `GridView` ne construit que ce qui est
    // visible, et un témoin qui cherche « Décembre » dans 800 × 600 ne mesure que la
    // paresse de la grille.
    tester.view.physicalSize = const Size(1440 * 2, 1000 * 2);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(sous(annee(), langue: const Locale('en')));
    await tester.pumpAndSettle();
    expect(find.text('January'), findsOneWidget);
    expect(find.text('December'), findsOneWidget);
  });

  /// Les tailles ne sont pas prises au hasard : 720 est le plancher de la fenêtre macOS,
  /// 1100 son ouverture par défaut, 1440 un écran courant, et 390 un téléphone — la vue
  /// est offerte partout, donc elle doit tenir partout.
  testWidgets('aucune largeur ne fait déborder la grille', (tester) async {
    for (final taille in [
      const Size(390, 760),
      const Size(720, 560),
      const Size(1100, 760),
      const Size(1440, 900),
      const Size(1920, 1200),
    ]) {
      tester.view.physicalSize = taille * 2;
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(sous(annee()));
      await tester.pumpAndSettle();

      // Un débordement de rendu ne lève rien : sans cette demande, le témoin passerait
      // sur une grille visiblement cassée.
      expect(
        tester.takeException(),
        isNull,
        reason: 'la grille déborde en ${taille.width} × ${taille.height}',
      );
    }
  });

  testWidgets('un jour du mois s\'ouvre, un jour voisin non', (tester) async {
    DateTime? choisi;
    await tester.pumpWidget(
      sous(annee(sur: DateTime(2026, 6, 15), surJour: (j) => choisi = j)),
    );
    await tester.pumpAndSettle();

    // Le 15 juin 2026 : un lundi, donc présent une seule fois dans sa propre grille —
    // mais « 15 » paraît douze fois dans l'année. On vise celui de juin par son mois.
    final juin = find.ancestor(
      of: find.text('Juin'),
      matching: find.byType(Column),
    );
    await tester.tap(
      find.descendant(of: juin.first, matching: find.text('15')).first,
    );
    await tester.pumpAndSettle();

    expect(choisi, isNotNull, reason: 'cliquer un jour doit l\'ouvrir');
    expect(choisi!.year, 2026);
    expect(choisi!.month, 6);
    expect(choisi!.day, 15);
  });

  testWidgets('aujourd\'hui se repère sans compter les cases', (tester) async {
    // Une fenêtre où les douze mois tiennent : `GridView` ne construit que ce qui est
    // visible, et un témoin qui cherche « Décembre » dans 800 × 600 ne mesure que la
    // paresse de la grille.
    tester.view.physicalSize = const Size(1440 * 2, 1000 * 2);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);

    final maintenant = DateTime.now();
    await tester.pumpWidget(sous(annee(sur: maintenant)));
    await tester.pumpAndSettle();

    // Le repère est un fond plein ; les autres jours n'en ont pas. Un seul jour de
    // l'année doit le porter — sinon « aujourd'hui » ne veut plus rien dire.
    final pastilles = tester
        .widgetList<Container>(find.byType(Container))
        .where(
          (c) =>
              c.decoration is BoxDecoration &&
              (c.decoration! as BoxDecoration).shape == BoxShape.circle &&
              (c.decoration! as BoxDecoration).color != null,
        );
    expect(
      pastilles.length,
      1,
      reason: 'un seul jour de l\'année est aujourd\'hui',
    );
  });
}
