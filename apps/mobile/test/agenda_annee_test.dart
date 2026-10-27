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

  Widget annee({
    DateTime? sur,
    ValueChanged<DateTime>? surJour,
    DateTime? aujourdhui,
  }) => GrilleDeLAnnee(
    annee: sur ?? DateTime(2026, 6, 15),
    premierJour: 1,
    surJour: surJour ?? (_) {},
    aujourdhui: aujourdhui,
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

  /// ─── Un repère, et un seul ───
  ///
  /// Ce témoin a existé en deux versions, et la première mérite d'être racontée parce
  /// qu'elle a coûté `main` rouge à trois sessions.
  ///
  /// Elle lisait `DateTime.now()`, comme la vue. Elle n'éprouvait donc que **le jour où
  /// elle tournait** : verte le 24 octobre 2026 avec le défaut en place, rouge le 26. Le
  /// défaut — le jour marqué dans les deux grilles qui le contiennent — ne se voit que si
  /// aujourd'hui tombe dans une semaine partagée par deux mois, soit environ une semaine
  /// sur quatre.
  ///
  /// Deux conséquences, et la seconde est la pire. Trois semaines sur quatre, un témoin
  /// vert disait que la question était réglée. Et la quatrième, il rendait `main` rouge
  /// **sans qu'une ligne ait changé** — personne ne cherche la cause d'une régression
  /// dans le calendrier.
  ///
  /// D'où l'horloge injectée. Les dates ci-dessous sont choisies et non prises au jour le
  /// jour : le témoin mord tous les jours, ou il ne sert à rien.
  group('aujourd\'hui se repère sans compter les cases', () {
    /// Compte les pastilles pleines : le repère est un fond plein, les autres jours n'en
    /// ont pas.
    int pastilles(WidgetTester tester) => tester
        .widgetList<Container>(find.byType(Container))
        .where(
          (c) =>
              c.decoration is BoxDecoration &&
              (c.decoration! as BoxDecoration).shape == BoxShape.circle &&
              (c.decoration! as BoxDecoration).color != null,
        )
        .length;

    Future<void> monter(WidgetTester tester, DateTime leJour) async {
      // Une fenêtre où les douze mois tiennent : `GridView` ne construit que ce qui est
      // visible, et compter les pastilles dans 800 × 600 ne mesure que la paresse de la
      // grille.
      tester.view.physicalSize = const Size(1440 * 2, 1000 * 2);
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(sous(annee(sur: leJour, aujourdhui: leJour)));
      await tester.pumpAndSettle();
    }

    /// Le cas qui a rendu `main` rouge. Le 27 octobre 2026 est un mardi ; novembre
    /// commence un dimanche, donc la première rangée de novembre montre le 26 au
    /// 31 octobre. Sans la condition `duMois`, le 27 s'allume **deux fois**.
    testWidgets('même dans une semaine partagée par deux mois', (tester) async {
      await monter(tester, DateTime(2026, 10, 27));
      expect(
        pastilles(tester),
        1,
        reason:
            'le 27 octobre 2026 paraît dans la grille d\'octobre et dans la première '
            'rangée de novembre : il ne doit s\'allumer que dans la sienne',
      );
    });

    /// L'autre bord de la même semaine, et dans l'autre sens : le 2 novembre 2026 est un
    /// lundi, donc la grille d'octobre le montre dans sa dernière rangée.
    testWidgets('et de l\'autre côté du partage', (tester) async {
      await monter(tester, DateTime(2026, 11, 2));
      expect(pastilles(tester), 1);
    });

    /// Un jour franchement au milieu d'un mois, qui ne paraît que dans sa grille. Ce cas
    /// passait **déjà** avec le défaut en place — il est là pour que l'absence de repère
    /// ne puisse pas passer pour un succès.
    testWidgets('comme au milieu d\'un mois', (tester) async {
      await monter(tester, DateTime(2026, 6, 15));
      expect(pastilles(tester), 1);
    });

    /// Une année qu'on regarde sans y être : aucun jour n'y est aujourd'hui, donc aucun
    /// repère. Sans ce cas, marquer le même numéro dans les douze mois passerait.
    testWidgets('et aucun repère sur une autre année', (tester) async {
      tester.view.physicalSize = const Size(1440 * 2, 1000 * 2);
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(
        sous(
          annee(sur: DateTime(2030, 3, 10), aujourdhui: DateTime(2026, 10, 27)),
        ),
      );
      await tester.pumpAndSettle();
      expect(pastilles(tester), 0);
    });
  });
}
