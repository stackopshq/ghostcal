import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ghostcal/l10n/generated/app_localisations.dart';
import 'package:ghostcal/main.dart';
import 'package:ghostcal/services/session.dart';
import 'package:ghostcal/services/verrouillage.dart';


/// L'application parle-t-elle les deux langues, et jusqu'au bout ?
///
/// ─── Ce que ce fichier gardait avant, et pourquoi il a changé ───
///
/// Il vérifiait que l'application ne déclarait **que** le français. C'était juste tant que
/// ses textes étaient en dur : déclarer l'anglais aurait donné des sélecteurs de date
/// anglais par-dessus des écrans français, un mélange pire que le tout-français. Le
/// fichier disait lui-même qu'il rougirait le jour de la traduction, et que ce serait le
/// moment de le relire. C'est ce jour-là.
///
/// ─── Les deux moitiés, qu'il ne faut pas confondre ───
///
/// · Les composants **fournis par Flutter** — sélecteurs, boutons de dialogue, étiquettes
///   d'accessibilité — viennent de `GlobalMaterialLocalizations`. Sans eux, un iPhone
///   réglé en français affichait « Select date », « Cancel », et des jours notés
///   S M T W T F S, au milieu d'écrans français.
/// · Les textes **de l'application** viennent de `L`, généré depuis `lib/l10n/*.arb`.
///
/// Les deux sont nécessaires. Traduire les nôtres sans les siens laisse les sélecteurs en
/// anglais ; l'inverse laisse les écrans en français. Ce fichier mesure les deux moitiés
/// dans les deux langues.
void main() {
  /// Monte l'application et rend le contexte d'un descendant de `MaterialApp`, seul
  /// endroit d'où `MaterialLocalizations.of` et `L.of` ont un sens.
  Future<BuildContext> monter(WidgetTester tester, Locale locale) async {
    late BuildContext interne;
    await tester.pumpWidget(
      GhostcalApp(
        session: Session(),
        verrouillage: Verrouillage(),
        locale: locale,
        // Un enfant à nous, pour ne dépendre d'aucun écran : ces tests portent sur la
        // langue, pas sur ce que montre la connexion.
        accueilDEpreuve: Builder(
          builder: (context) {
            interne = context;
            return const SizedBox.shrink();
          },
        ),
      ),
    );
    return interne;
  }

  group('les composants de Flutter suivent la langue', () {
    testWidgets('en français', (tester) async {
      final l10n = MaterialLocalizations.of(await monter(tester, const Locale('fr')));
      expect(l10n.cancelButtonLabel, 'Annuler');
      expect(l10n.narrowWeekdays, contains('L'));
      expect(l10n.formatMonthYear(DateTime(2026, 2, 1)), contains('février'));
    });

    testWidgets('en anglais', (tester) async {
      final l10n = MaterialLocalizations.of(await monter(tester, const Locale('en')));
      expect(l10n.cancelButtonLabel, 'Cancel');
      expect(l10n.formatMonthYear(DateTime(2026, 2, 1)), contains('February'));
    });
  });

  group("les textes de l'application suivent la langue", () {
    testWidgets('en français', (tester) async {
      final l = L.of(await monter(tester, const Locale('fr')));
      expect(l.ongletReunions, 'Réunions');
      expect(l.contenuIllisible, 'Contenu illisible — clé manquante');
    });

    testWidgets('en anglais', (tester) async {
      final l = L.of(await monter(tester, const Locale('en')));
      expect(l.ongletReunions, 'Meetings');
      expect(l.contenuIllisible, 'Unreadable content — key missing');
    });
  });

  testWidgets('les deux langues sont déclarées, et elles viennent des .arb', (tester) async {
    await monter(tester, const Locale('fr'));
    final app = tester.widget<MaterialApp>(find.byType(MaterialApp));

    // La liste vient de `L.supportedLocales`, donc des fichiers `.arb`. La recopier à la
    // main laisserait une langue traduite mais non chargée — et rien ne le dirait.
    expect(
      app.supportedLocales.map((l) => l.languageCode).toSet(),
      {'fr', 'en'},
      reason: 'GhostPass livre FR et EN sur iOS comme sur Android.',
    );
    expect(app.supportedLocales, same(L.supportedLocales));
  });

  testWidgets("une langue inconnue retombe sur le français, pas sur l'anglais",
      (tester) async {
    // Le repli par défaut de Flutter est la **première** langue de la liste. Celle-ci est
    // ordonnée par `gen-l10n` et rien ne garantit qu'elle commence par le français : le
    // vérifier ici évite qu'un appareil réglé en allemand se retrouve en anglais, dans un
    // produit écrit en français et vendu en Suisse romande.
    final l = L.of(await monter(tester, const Locale('de')));
    expect(l.ongletReunions, 'Réunions');
  });

  test('aucun message ne reste sans traduction', () {
    // `gen-l10n` écrit ici les clés présentes en français et absentes en anglais. Un
    // fichier non vide veut dire que l'application anglaise affiche des phrases
    // françaises — le repli est silencieux, c'est pourquoi on le mesure.
    final rapport = File('lib/l10n/non-traduit.json');
    expect(rapport.existsSync(), isTrue,
        reason: 'lib/l10n/non-traduit.json est absent : lancez `flutter gen-l10n`. '
            "Sans ce fichier, ce test ne mesure rien.");
    expect(
      jsonDecode(rapport.readAsStringSync()),
      isEmpty,
      reason: 'Des messages du français manquent en anglais.',
    );
  });
}
