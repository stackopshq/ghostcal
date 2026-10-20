// Verrouiller doit retirer ce qui est à l'écran, pas seulement fermer le coffre.
//
// ─── Le défaut que ce témoin garde ───
//
// `main.dart` bascule `home` vers l'écran de connexion quand le coffre se ferme. Mais les
// écrans ouverts par `Navigator.push` vivent **au-dessus** de `home`, dans le même
// navigateur : changer `home` ne les retire pas. Un événement ouvert, une fiche, la
// recherche restaient donc affichés — déchiffrés — par-dessus un coffre verrouillé.
//
// Sur iOS, le chemin le plus banal n'est pas le bouton « Verrouiller » : c'est le
// verrouillage automatique au retour d'arrière-plan, qui emprunte le même appel. Il
// suffisait de quitter l'application en laissant une fiche ouverte.
//
// ─── Pourquoi ce fichier existe alors que macOS a déjà le sien ───
//
// La correction est dans du code partagé ; son témoin ne l'était pas. Il vit dans
// `integration_test/macos_test.dart`, et ne tourne donc que sur macOS. Une régression
// introduite sur iOS passerait au vert partout où on la cherche.
//
// ─── Pourquoi un témoin d'intégration et non un `flutter test` ───
//
// Le garde ne se déclenche qu'au **passage** de `Etat.ouvert` à autre chose, et seule une
// vraie ouverture de coffre atteint `ouvert` : elle demande le cœur Rust et un serveur.
// Un témoin hors matériel ne pourrait que simuler l'état qu'il prétend éprouver.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:ghostcal/main.dart';
import 'package:ghostcal/services/apparence.dart';
import 'package:ghostcal/services/session.dart';
import 'package:ghostcal/services/verrouillage.dart';
import 'package:ghostcal/src/rust/frb_generated.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  const serveur = String.fromEnvironment('GHOSTCAL_SERVEUR');
  const email = String.fromEnvironment('GHOSTCAL_EMAIL');
  const phrase = String.fromEnvironment('GHOSTCAL_PHRASE');

  setUpAll(() async {
    expect(serveur, isNotEmpty, reason: 'GHOSTCAL_SERVEUR manquant (--dart-define)');
    await RustLib.init();
  });

  testWidgets('verrouiller retire les écrans empilés', (tester) async {
    final session = Session();
    await session.amorcer();
    final verrouillage = Verrouillage();
    await verrouillage.amorcer();
    final apparence = Apparence();
    await apparence.amorcer();

    await tester.pumpWidget(GhostcalApp(
      session: session,
      verrouillage: verrouillage,
      apparence: apparence,
    ));
    await tester.pumpAndSettle();

    // ── Ouvrir le coffre ──
    if (find.byKey(const Key('champ.serveur')).evaluate().isNotEmpty) {
      await tester.enterText(find.byKey(const Key('champ.serveur')), serveur);
      await tester.enterText(find.byKey(const Key('champ.email')), email);
    }
    await tester.enterText(find.byKey(const Key('champ.phrase')), phrase);
    await tester.pumpAndSettle();
    await tester.testTextInput.receiveAction(TextInputAction.done);

    final limite = DateTime.now().add(const Duration(seconds: 40));
    while (find.byKey(const Key('accueil.pret')).evaluate().isEmpty) {
      if (DateTime.now().isAfter(limite)) {
        fail('Le coffre ne s\'est pas ouvert sur $serveur en 40 s. '
            'Le banc est-il allumé (tools/banc-local.sh) ?');
      }
      await tester.pump(const Duration(milliseconds: 250));
      await Future<void>.delayed(const Duration(milliseconds: 250));
    }
    await tester.pumpAndSettle();
    expect(session.etat, Etat.ouvert);

    // ── Empiler un écran : Réglages, puis Profil ──
    await tester.tap(find.byKey(const Key('accueil.menu')));
    await tester.pumpAndSettle();
    // Les deux langues : l'application garde celle choisie au dernier lancement, et ce
    // témoin n'a pas à dépendre de ce qu'une autre exécution a laissé dans le trousseau.
    final reglages = [
      find.text('Réglages'),
      find.text('Settings'),
    ].firstWhere((f) => f.evaluate().isNotEmpty,
        orElse: () => fail('Ni « Réglages » ni « Settings » dans le menu — '
            'la navigation du lot C a-t-elle encore changé ?'));
    await tester.tap(reglages.last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('reglages.serveur')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('reglages.serveur')));
    await tester.pumpAndSettle();

    // Le dialogue du changement de serveur est poussé par-dessus : il fait un écran
    // empilé parfaitement ordinaire, et il porte une clé stable.
    expect(find.byKey(const Key('reglages.serveur.confirmer')), findsOneWidget,
        reason: 'Rien n\'est empilé : le témoin ne mesurerait plus rien.');

    // ── Verrouiller, sans toucher à l'écran empilé ──
    session.verrouiller();
    await tester.pumpAndSettle();

    expect(session.etat, isNot(Etat.ouvert));
    expect(
      find.byKey(const Key('reglages.serveur.confirmer')),
      findsNothing,
      reason: 'L\'écran empilé est resté par-dessus un coffre verrouillé. C\'est le '
          'défaut que `_RetirerLesEcransAuVerrouillage` corrige, et la fuite se voit '
          'surtout sur une fiche d\'événement, dont le contenu est déchiffré.',
    );
    expect(find.byKey(const Key('champ.phrase')), findsOneWidget,
        reason: 'Après verrouillage, c\'est l\'écran de connexion qu\'on doit voir.');
  }, timeout: const Timeout(Duration(minutes: 3)));
}
