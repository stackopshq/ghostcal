import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ghostcal/main.dart';
import 'package:ghostcal/services/session.dart';
import 'package:ghostcal/services/verrouillage.dart';

/// Les composants que Flutter fournit parlent-ils français ?
///
/// Ce n'est pas la même question que « l'application est-elle en français ». Ses propres
/// textes le sont, en dur, depuis toujours. Mais le sélecteur de date, le sélecteur
/// d'heure, les boutons d'un dialogue et les étiquettes d'accessibilité viennent de
/// `MaterialLocalizations` — et sans `flutter_localizations`, ils restent **en anglais**
/// sur un iPhone pourtant réglé en français.
///
/// Le symptôme est un écran à moitié traduit, sur le parcours principal du produit :
/// « Nouvel événement », puis « Select date », « CANCEL », « OK ». C'est ce que verrait
/// l'examinateur d'Apple en premier.
///
/// Ces tests ne mesurent pas la configuration — ils interrogent l'arbre de widgets tel
/// qu'il est construit. Retirer les `localizationsDelegates` de `main.dart` les fait
/// rougir ; les y remettre les fait reverdir. Éprouvé dans les deux sens le
/// 25 septembre 2026.
void main() {
  /// Monte l'application et rend le contexte d'un descendant de `MaterialApp`, seul
  /// endroit d'où `MaterialLocalizations.of` a un sens.
  Future<BuildContext> monterEtDescendre(WidgetTester tester) async {
    late BuildContext interne;
    await tester.pumpWidget(
      GhostcalApp(
        session: Session(),
        verrouillage: Verrouillage(),
        // Un enfant à nous, pour ne dépendre d'aucun écran : ces tests portent sur la
        // langue, pas sur ce que montre la connexion. Si l'écran d'accueil change, ils
        // ne doivent pas rougir pour autant.
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

  testWidgets('les composants de Material parlent français', (tester) async {
    final context = await monterEtDescendre(tester);
    final l10n = MaterialLocalizations.of(context);

    // Trois libellés que l'utilisateur rencontre sur le parcours de création d'un
    // événement. Ils viennent tous de Flutter, aucun du dépôt : si l'un d'eux est en
    // anglais, `flutter_localizations` n'est pas branché.
    expect(l10n.cancelButtonLabel, 'Annuler');
    expect(l10n.okButtonLabel, 'OK');
    expect(l10n.datePickerHelpText, isNot(equals('Select date')));
  });

  testWidgets('les noms de jours et de mois sont français', (tester) async {
    final context = await monterEtDescendre(tester);
    final l10n = MaterialLocalizations.of(context);

    // `narrowWeekdays` commence au dimanche chez Material. On vérifie le contenu, pas
    // l'ordre : c'est la langue qu'on mesure.
    expect(l10n.narrowWeekdays, contains('L'));
    expect(l10n.formatMonthYear(DateTime(2026, 2, 1)), contains('février'));
  });

  testWidgets(
    "l'application ne déclare que le français, et le déclare explicitement",
    (tester) async {
      await monterEtDescendre(tester);
      final app = tester.widget<MaterialApp>(find.byType(MaterialApp));

      // Déclarer l'anglais ferait basculer les composants système en anglais sur un
      // appareil réglé ainsi, pendant que les textes de l'application resteraient
      // français — un mélange pire que le tout-français. Le jour où ces textes seront
      // extraits en `.arb`, cette liste s'allongera en même temps qu'eux ; ce test
      // rougira alors, et c'est à ce moment-là qu'il faudra le relire.
      expect(app.supportedLocales.map((l) => l.languageCode), ['fr']);
      // `locale` imposée, et pas seulement « soutenue » : sans elle, un appareil réglé
      // dans une langue non soutenue retomberait sur la première de la liste par
      // résolution implicite. Le résultat serait le même aujourd'hui, mais par accident.
      expect(app.locale, const Locale('fr'));
    },
  );
}
