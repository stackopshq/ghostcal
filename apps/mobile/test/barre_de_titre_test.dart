import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/main.dart';
import 'package:ghostcal/services/session.dart';
import 'package:ghostcal/services/verrouillage.dart' as v;

/// Ce qui est poussé par-dessus l'accueil doit commencer **sous** la barre de titre.
///
/// ─── Le défaut que ce témoin garde ───
///
/// `MainFlutterWindow` rend la barre de titre transparente et fait passer la vue Flutter
/// dessous, pour que la barre d'outils de l'accueil se tienne sur la même ligne que les
/// trois pastilles de la fenêtre. Tout écran poussé héritait de cela sans l'avoir
/// demandé : il commençait à y = 0, et sa flèche de retour se posait exactement sous les
/// pastilles — mesurées à x = 18 … 80 sur la machine.
///
/// Le bouton restait visible et devenait inatteignable. Rien ne le disait : ni erreur,
/// ni avertissement, ni débordement. Vu en capture, pas en test.
void main() {
  Widget pousse(Widget suivant) => Builder(
    builder: (context) => Scaffold(
      body: Center(
        child: TextButton(
          onPressed: () =>
              Navigator.of(context)
                  .push(MaterialPageRoute<void>(builder: (_) => suivant)),
          child: const Text('ouvrir'),
        ),
      ),
    ),
  );

  Future<void> monter(WidgetTester tester, Widget accueil) => tester.pumpWidget(
    GhostcalApp(
      session: Session(),
      verrouillage: v.Verrouillage(),
      accueilDEpreuve: accueil,
    ),
  );

  testWidgets('sur macOS, un écran poussé descend sous les pastilles', (
    tester,
  ) async {
    // Remise dans le corps et non par `addTearDown` : la vérification d'invariants de
    // Flutter passe **avant** les démontages, et refuse une variable de débogage laissée
    // en place — « The value of a foundation debug variable was changed by the test ».
    debugDefaultTargetPlatformOverride = TargetPlatform.macOS;
    await monter(
      tester,
      pousse(
        Scaffold(
          appBar: AppBar(title: const Text('détail')),
          body: const SizedBox(),
        ),
      ),
    );
    await tester.tap(find.text('ouvrir'));
    await tester.pumpAndSettle();

    final fleche = tester.getRect(find.byType(BackButton));
    debugDefaultTargetPlatformOverride = null;
    expect(
      fleche.top,
      greaterThanOrEqualTo(52.0),
      reason:
          'la flèche de retour est sous les pastilles de la fenêtre, '
          'donc inatteignable',
    );
  });

  /// La même application sur un téléphone ne doit pas gagner 52 points de vide : la
  /// barre de titre n'existe que sur macOS, et réserver sa place ailleurs serait un
  /// bandeau sans raison en haut de chaque écran.
  testWidgets('et nulle part ailleurs', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    await monter(
      tester,
      pousse(
        Scaffold(
          appBar: AppBar(title: const Text('détail')),
          body: const SizedBox(),
        ),
      ),
    );
    await tester.tap(find.text('ouvrir'));
    await tester.pumpAndSettle();

    final haut = tester.getRect(find.byType(BackButton)).top;
    debugDefaultTargetPlatformOverride = null;
    expect(haut, lessThan(52.0));
  });
}
