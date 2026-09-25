import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:ghostcal/main.dart';
import 'package:ghostcal/services/session.dart';
import 'package:ghostcal/services/verrouillage.dart';
import 'package:ghostcal/src/rust/frb_generated.dart';

/// Promène l'application devant l'objectif, pour la fiche App Store.
///
///     tools/ios/captures-appstore.sh
///
/// ─── Qui appuie sur le déclencheur ───
///
/// Pas ce fichier. Il **demande** une prise de vue en déposant un fichier témoin dans son
/// propre dossier temporaire, puis attend que l'hôte l'efface. L'hôte, lui, surveille ce
/// dossier — accessible depuis le Mac par `xcrun simctl get_app_container` — et tire au
/// `simctl io … screenshot`.
///
/// Ce détour existe pour une raison mesurable : `binding.takeScreenshot()` rend la surface
/// Flutter, dont les dimensions suivent le rendu logique. App Store Connect exige les
/// dimensions **natives** de la dalle et refuse toute image redimensionnée après coup.
/// Seul `simctl` les produit.
///
/// ─── Ce que ce scénario ne photographie pas, et pourquoi ───
///
/// **Réunions** et **Sondages** sont absents. Ce n'est pas un oubli : `tools/banc-local.sh`
/// n'amorce ni réservation ni sondage — mesuré, `/v1/me/meetings` et `/v1/me/polls` rendent
/// des listes vides. Les photographier donnerait deux écrans d'état vide en vitrine, ce qui
/// est pire que deux captures en moins.
///
/// Les ajouter demande d'amorcer une réservation depuis la page publique et un sondage avec
/// des votes. C'est un travail sur le banc, pas sur ce fichier.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  const serveur = String.fromEnvironment('GHOSTCAL_SERVEUR');
  const email = String.fromEnvironment('GHOSTCAL_EMAIL');
  const phrase = String.fromEnvironment('GHOSTCAL_PHRASE');

  /// Le dossier d'échange avec l'hôte. `Directory.systemTemp` pointe vers le `tmp` du
  /// conteneur de données de l'application, que le Mac atteint par
  /// `xcrun simctl get_app_container <appareil> ch.stackops.ghostcal data`.
  final echange = Directory('${Directory.systemTemp.path}/ghostcal-captures');

  /// Demande une prise de vue et attend qu'elle ait eu lieu.
  ///
  /// Rend la main dès que l'hôte a effacé le témoin. Au bout de 30 secondes sans réponse,
  /// **échoue** au lieu de continuer : une prise de vue silencieusement sautée donnerait
  /// une suite verte et un jeu de captures incomplet, ce qui est exactement le défaut
  /// qu'on cherche à éviter.
  Future<void> photographier(WidgetTester tester, String nom) async {
    // Laisser la transition se terminer **sur la dalle**, pas seulement dans l'arbre de
    // widgets. `pumpAndSettle` rend la main dès que Flutter n'a plus d'animation en
    // attente ; la couche de composition du simulateur, elle, a encore des images à
    // présenter.
    //
    // Mesuré : avec 600 ms, la capture « 02-nouvel-evenement » sortait **en pleine
    // transition de page** — fond noir au lieu du fond clair, titre et libellés à demi
    // opaques. L'image avait la bonne taille, des milliers de teintes, et passait tous
    // les contrôles automatiques. Seule l'ouvrir l'a montrée.
    //
    // C'est le défaut type : une image qui se lit comme une capture tant qu'on ne la
    // regarde pas. Deux secondes coûtent dix secondes sur l'ensemble du jeu.
    await tester.pumpAndSettle();
    await Future<void>.delayed(const Duration(seconds: 2));
    await tester.pumpAndSettle();

    echange.createSync(recursive: true);
    final temoin = File('${echange.path}/$nom.demande');
    temoin.writeAsStringSync(nom);

    final limite = DateTime.now().add(const Duration(seconds: 30));
    while (temoin.existsSync()) {
      if (DateTime.now().isAfter(limite)) {
        fail(
          "L'hôte n'a pas répondu à la demande de capture « $nom » en 30 s. "
          "Le dossier d'échange est ${echange.path} ; c'est là que "
          'tools/ios/captures-appstore.sh doit regarder.',
        );
      }
      // On continue à pomper pendant l'attente : une application figée pendant que l'hôte
      // photographie donnerait une image de transition.
      await tester.pump(const Duration(milliseconds: 100));
      await Future<void>.delayed(const Duration(milliseconds: 100));
    }
  }

  setUpAll(() async {
    expect(serveur, isNotEmpty, reason: 'GHOSTCAL_SERVEUR manquant (--dart-define)');
    expect(email, isNotEmpty, reason: 'GHOSTCAL_EMAIL manquant (--dart-define)');
    expect(phrase, isNotEmpty, reason: 'GHOSTCAL_PHRASE manquant (--dart-define)');
    await RustLib.init();
    if (echange.existsSync()) echange.deleteSync(recursive: true);
  });

  testWidgets('le tour de la boutique', (tester) async {
    final session = Session();
    await session.amorcer();
    final verrouillage = Verrouillage();
    await verrouillage.amorcer();
    await tester.pumpWidget(
      GhostcalApp(session: session, verrouillage: verrouillage),
    );
    await tester.pumpAndSettle();

    // ── Connexion ──
    //
    // Les trois champs portent des clés stables, employées aussi par `test/connexion_test`.
    // Passer par les libellés ferait dépendre la prise de vue d'un texte d'interface.
    await tester.enterText(find.byKey(const Key('champ.serveur')), serveur);
    await tester.enterText(find.byKey(const Key('champ.email')), email);
    await tester.enterText(find.byKey(const Key('champ.phrase')), phrase);
    await tester.pumpAndSettle();

    // On valide au clavier plutôt qu'en touchant « Se connecter », et ce n'est pas un
    // contournement : c'est le seul chemin fiable, pour une raison qui mérite d'être
    // écrite.
    //
    // Le bouton est désactivé tant que `_phrase.text` est vide — mais `_phrase` n'a
    // **aucun écouteur**, et rien dans `connexion.dart` ne reconstruit la carte quand le
    // texte change. Dans l'application, il se réactive quand même : le clavier logiciel
    // qui se lève modifie `MediaQuery.viewInsets`, ce qui déclenche une reconstruction.
    // L'état du bouton dépend donc d'un effet de bord du clavier, pas du texte saisi.
    //
    // `enterText` ne lève aucun clavier. Le bouton restait désactivé, le clic tombait sur
    // un `IgnorePointer`, et `flutter_test` ne le signalait qu'en **avertissement** — le
    // scénario continuait comme si de rien n'était, jusqu'à expirer quarante secondes plus
    // tard sur un écran de connexion.
    //
    // `receiveAction(done)` emprunte `onSubmitted`, qui appelle `_valider()` directement.
    // C'est ce que fait un utilisateur qui appuie sur Entrée.
    await tester.testTextInput.receiveAction(TextInputAction.done);

    // La connexion parle au réseau : `pumpAndSettle` seul rendrait la main avant la
    // réponse. On attend que l'écran d'accueil paraisse, et on **échoue** s'il ne paraît
    // pas — plutôt que de photographier un écran de connexion en croyant tenir l'agenda.
    final limite = DateTime.now().add(const Duration(seconds: 40));
    while (find.text('Agenda').evaluate().isEmpty) {
      if (DateTime.now().isAfter(limite)) {
        fail(
          'La connexion à $serveur n\'a pas abouti en 40 s. Le banc est-il allumé '
          '(tools/banc-local.sh) ? Le simulateur atteint 127.0.0.1 directement.',
        );
      }
      await tester.pump(const Duration(milliseconds: 250));
      await Future<void>.delayed(const Duration(milliseconds: 250));
    }
    await tester.pumpAndSettle();

    // ── 01 · Agenda ──
    await photographier(tester, '01-agenda');

    // ── 02 · Nouvel événement ──
    //
    // La capture la plus importante du jeu : c'est l'écran qui porte la phrase expliquant
    // ce qui est chiffré et ce qui ne l'est pas — l'argument du produit. Le bouton flottant
    // n'existe que s'il y a un calendrier inscriptible ; s'il manque, on le dit.
    final ajouter = find.byType(FloatingActionButton);
    expect(
      ajouter,
      findsOneWidget,
      reason: "Pas de bouton « + » sur l'agenda : le compte du banc n'a aucun calendrier "
          'inscriptible, et la capture 02 serait impossible.',
    );
    await tester.tap(ajouter);
    await tester.pumpAndSettle();
    await photographier(tester, '02-nouvel-evenement');

    // `tester.pageBack()` cherche un `BackButton`, un `CloseButton` ou un
    // `CupertinoNavigationBarBackButton`. L'écran de création n'en porte aucun : sa
    // flèche de retour est dessinée par la charte, pas par Material. `pageBack` échouait
    // donc sur « One back button expected on screen ».
    //
    // On dépile par le navigateur, ce qui ne dépend d'aucune apparence.
    tester.state<NavigatorState>(find.byType(Navigator).first).pop();
    await tester.pumpAndSettle();

    // ── 03 · Tâches ──
    await tester.tap(find.text('Tâches'));
    await tester.pumpAndSettle();
    await photographier(tester, '03-taches');

    // ── 04 · Liens de réservation ──
    await tester.tap(find.text('RDV'));
    await tester.pumpAndSettle();
    await photographier(tester, '04-rendez-vous');

    // ── 05 · Réglages ──
    //
    // Retenu plutôt que « Réunions » : celui-ci a du contenu (organisation, disponibilités,
    // sécurité), l'autre serait vide faute d'amorçage.
    await tester.tap(find.text('Réglages'));
    await tester.pumpAndSettle();
    await photographier(tester, '05-reglages');
  }, timeout: const Timeout(Duration(minutes: 5)));
}
