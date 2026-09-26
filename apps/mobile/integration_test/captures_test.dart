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
/// ─── Le jeu de données ───
///
/// Ce scénario suppose `./tools/banc-local.sh --vitrine`, et **pas** le banc d'épreuve.
/// Celui-ci dépose exprès un événement scellé sous une autre clé, qui s'affiche en rouge
/// « Contenu illisible — clé manquante » : un comportement juste, qu'on veut éprouver, et
/// qui en devanture se lit comme un bogue. La première version de ces captures en portait
/// une, sur une journée à deux entrées laissant les deux tiers de l'écran vides.
///
/// Le jeu de vitrine amorce en plus un horaire de disponibilité, une réunion réellement
/// réservée depuis la page publique et un sondage voté — sans quoi « Réunions » et
/// « Sondages » seraient des écrans vides.
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

    // On valide au clavier plutôt qu'en touchant « Se connecter ».
    //
    // Ce qui est **mesuré** : toucher le bouton ne déclenchait rien. `flutter_test` le
    // signalait — « derived an Offset that would not hit test on the specified widget » —
    // et le résultat du test de frappe montrait un `IgnorePointer`, donc un bouton
    // désactivé. Le scénario continuait malgré tout, parce que c'est un **avertissement**
    // et non une erreur, jusqu'à expirer quarante secondes plus tard sur l'écran de
    // connexion. Un clic qui ne clique pas et ne se plaint qu'en passant.
    //
    // Ce qui **n'est pas établi** : pourquoi. `_champDePhrase` porte bien un
    // `onChanged: (_) => setState(() {})`, qui devrait rallumer le bouton dès la première
    // frappe. La première version de ce commentaire affirmait le contraire — que rien ne
    // reconstruisait la carte — et c'était faux : je ne l'avais pas lu.
    //
    // `receiveAction(done)` emprunte `onSubmitted`, qui appelle `_valider()` directement.
    // C'est le geste d'un utilisateur qui appuie sur Entrée, et il ne dépend d'aucun état
    // de bouton. À préférer ici pour cette seule raison — pas parce que le bouton serait
    // cassé dans le produit : rien ne l'a montré.
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

    // ── 04 · Réunions réservées ──
    //
    // L'écran que le jeu d'épreuve ne pouvait pas montrer : il faut une réservation prise
    // depuis la page publique, donc un horaire de disponibilité, que le banc d'épreuve ne
    // posait pas.
    await tester.tap(find.text('Réunions'));
    await tester.pumpAndSettle();
    await photographier(tester, '04-reunions');

    // ── 05 · Liens de réservation ──
    await tester.tap(find.text('RDV'));
    await tester.pumpAndSettle();
    await photographier(tester, '05-rendez-vous');

    // ── 06 · Réglages ──
    //
    // La sixième est **facultative** : Apple en accepte dix, et celle-ci montre le compte,
    // les disponibilités et la sécurité. À garder ou à écarter au montage de la fiche.
    await tester.tap(find.text('Réglages'));
    await tester.pumpAndSettle();
    await photographier(tester, '06-reglages');
  }, timeout: const Timeout(Duration(minutes: 5)));
}
