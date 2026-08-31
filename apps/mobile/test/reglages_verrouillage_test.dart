import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/ecrans/reglages.dart';
import 'package:ghostcal/services/session.dart';
import 'package:ghostcal/services/verrouillage.dart' as v;

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
    await tester.pumpWidget(MaterialApp(
      home: EcranDeReglages(session: Session(), verrouillage: verrouillage),
    ));
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
}
