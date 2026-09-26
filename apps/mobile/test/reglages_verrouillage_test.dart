import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/ecrans/reglages.dart';
import 'package:ghostcal/services/session.dart';
import 'package:ghostcal/services/verrouillage.dart' as v;
import 'harnais.dart';

/// Ce test monte **l'écran réel**, pas une maquette qui lui ressemble.
///
/// La version précédente reconstruisait le même `RadioGroup` dans un `Scaffold` nu : elle
/// passait au vert pendant que l'écran livré, lui, ne sélectionnait rien. Un témoin qui
/// reconstruit son sujet ne teste que la copie.
///
/// `Session()` sans `api` fait sortir `_charger` immédiatement — les sections Organisation
/// et Disponibilités restent sur leur indicateur, et la section Sécurité, elle, se construit
/// exactement comme en production.
void main() {
  testWidgets('choisir un délai déplace la sélection', (tester) async {
    final verrouillage = v.Verrouillage();
    await tester.pumpWidget(
        appDEpreuve(EcranDeReglages(session: Session(), verrouillage: verrouillage)));
    await tester.pump();

    // Pas de `pumpAndSettle` : les deux sections encore en chargement animent un
    // `LinearProgressIndicator` qui ne s'arrête jamais, et l'attente expirerait sans
    // qu'aucune faute ne soit en cause. On avance d'images comptées.
    // `scrollUntilVisible` s'arrête dès que le finder **trouve** la tuile — or un
    // `ListView` la construit avant qu'elle entre dans la fenêtre. Le premier essai
    // appuyait donc à 734 px dans une fenêtre haute de 600, et le raté ressemblait
    // trait pour trait au défaut cherché. `ensureVisible` va jusqu'à la faire voir.
    await tester.ensureVisible(find.text('Après 5 minutes'));
    await tester.pump();
    await tester.tap(find.text('Après 5 minutes'), warnIfMissed: true);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(verrouillage.choix, v.DelaiDeVerrouillage.cinqMinutes);
    expect(verrouillage.cadenasVisible, isTrue);
  });

  /// L'ordre des sections, et l'unicité de leurs titres.
  ///
  /// Le témoin que j'aurais voulu écrire — « les quatre délais sont visibles sans
  /// défiler » — **ne sait pas rougir** : dans un test, les sections Organisation et
  /// Disponibilités n'ont pas de serveur, se réduisent à un indicateur, et la liste tient
  /// alors dans la fenêtre quel que soit son ordre. Il passait au vert sur l'écran fautif.
  /// Un témoin vert des deux côtés ne dit rien ; celui-ci le remplace.
  ///
  /// Ce qu'il retient du défaut, lui, est vérifiable : la section Sécurité arrivait en
  /// **dernier**, derrière deux en-têtes portant le même titre, et se faisait couper juste
  /// sous « Immédiatement ». Une section coupée après son premier élément se lit comme
  /// complète — Clara en a conclu, à raison, qu'aucun autre délai n'était proposé, alors
  /// que les quatre tuiles étaient bel et bien construites.
  ///
  /// Reste non couvert, et il vaut mieux l'écrire : que la section **tienne** à l'écran
  /// une fois les données chargées. Cela demanderait d'injecter les services dans l'écran,
  /// ce qu'il ne permet pas aujourd'hui.
  testWidgets('Sécurité passe avant le reste, et aucun titre ne se répète',
      (tester) async {
    // Une fenêtre haute, et ce n'est pas un détail d'instrument : le relevé ci-dessous ne
    // voit que les `Text` **construits**, et un `ListView` n'en construit que le voisinage
    // de sa fenêtre. Dans les 600 px par défaut, ajouter une tuile à la section Sécurité
    // suffisait à faire sortir « ORGANISATION » du relevé — `indexOf` rendait alors -1, et
    // le témoin échouait en désignant un ordre inversé qui n'existait pas. Le message
    // accusait l'écran d'un défaut qui était dans la mesure.
    tester.view.physicalSize = const Size(800, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
        appDEpreuve(EcranDeReglages(session: Session(), verrouillage: v.Verrouillage())));
    await tester.pump();

    final titres = <String>[];
    for (final e in find.byType(Text).evaluate()) {
      final t = (e.widget as Text).data;
      // Les en-têtes de section sont les seuls textes entièrement capitalisés.
      if (t != null && t.isNotEmpty && t == t.toUpperCase() && t.length > 3) {
        titres.add(t);
      }
    }

    expect(titres.toSet().length, titres.length,
        reason: 'deux sections portent le même titre : $titres');
    expect(titres.indexOf('SÉCURITÉ'), lessThan(titres.indexOf('ORGANISATION')),
        reason: 'la sécurité doit précéder le reste : $titres');
  });
}
