// Les écrans, dans les quatre combinaisons de langue et de thème.
//
// ─── Ce qu'il cherche ───
//
// Un libellé oublié en dur dans une langue, et un écran qui casse en sombre. Les deux se
// voient à l'œil et se ratent à la relecture : il y a cinq onglets et deux cent cinquante
// chaînes.
//
// Le témoin **traverse** les cinq onglets dans chaque combinaison, plutôt que de se
// contenter de poser le thème : un écran qui lève une exception ne la lève qu'une fois
// construit, et `flutter_test` ne rougit que si la construction a lieu.
//
// ─── Pourquoi des captures en plus des assertions ───
//
// Une assertion sait dire « le libellé est traduit ». Elle ne sait pas dire « le texte
// gris sur fond gris ne se lit pas ». Une capture par combinaison, prise par `simctl`,
// laisse l'œil trancher ce que l'assertion ne couvre pas — selon le même protocole que
// `captures_test.dart`, dont l'en-tête explique pourquoi l'hôte tient l'appareil photo.

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:ghostcal/main.dart';
import 'package:ghostcal/services/apparence.dart';
import 'package:ghostcal/services/rappels.dart';
import 'package:ghostcal/services/session.dart';
import 'package:ghostcal/services/verrouillage.dart';
import 'package:ghostcal/src/rust/frb_generated.dart';

/// Les cinq onglets, dans les deux langues. L'ordre suit celui de la barre.
const onglets = {
  ChoixDeLangue.francais: ['Agenda', 'Tâches', 'Réunions', 'RDV', 'Réglages'],
  ChoixDeLangue.anglais: ['Calendar', 'Tasks', 'Meetings', 'Links', 'Settings'],
};

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  const serveur = String.fromEnvironment('GHOSTCAL_SERVEUR');
  const email = String.fromEnvironment('GHOSTCAL_EMAIL');
  const phrase = String.fromEnvironment('GHOSTCAL_PHRASE');

  final echange = Directory('${Directory.systemTemp.path}/ghostcal-captures');

  Future<void> photographier(WidgetTester tester, String nom) async {
    await tester.pumpAndSettle();
    await Future<void>.delayed(const Duration(seconds: 2));
    await tester.pumpAndSettle();

    echange.createSync(recursive: true);
    final temoin = File('${echange.path}/$nom.demande');
    temoin.writeAsStringSync(nom);

    final limite = DateTime.now().add(const Duration(seconds: 30));
    while (temoin.existsSync()) {
      if (DateTime.now().isAfter(limite)) {
        fail("L'hôte n'a pas répondu à la demande de capture « $nom » en 30 s.");
      }
      await tester.pump(const Duration(milliseconds: 100));
      await Future<void>.delayed(const Duration(milliseconds: 100));
    }
  }

  setUpAll(() async {
    expect(serveur, isNotEmpty, reason: 'GHOSTCAL_SERVEUR manquant (--dart-define)');
    await RustLib.init();
    if (echange.existsSync()) echange.deleteSync(recursive: true);
  });

  testWidgets('les cinq onglets tiennent en clair et en sombre, en français et en anglais',
      (tester) async {
    final session = Session();
    await session.amorcer();
    final verrouillage = Verrouillage();
    await verrouillage.amorcer();
    final apparence = Apparence();
    await apparence.amorcer();
    // Les rappels sont passés comme `main()` les passe sur iOS depuis la parité : sans
    // eux, la section « Rappels » n'existe pas dans l'arbre et les captures ne diraient
    // rien de ses libellés, qui sont neufs dans les deux langues.
    final rappels = Rappels();
    await rappels.amorcer();

    await tester.pumpWidget(GhostcalApp(
      session: session,
      verrouillage: verrouillage,
      apparence: apparence,
      rappels: rappels,
    ));
    await tester.pumpAndSettle();

    // ── Connexion ──
    //
    // Même geste que `captures_test.dart` : on valide au clavier, parce que toucher
    // « Se connecter » n'a pas déclenché l'action — voir l'en-tête de ce fichier-là, qui
    // garde la mesure et s'abstient de conclure sur la cause.
    // L'écran de connexion a trois visages, et celui-ci dépend de ce qu'une exécution
    // précédente a laissé dans le trousseau : une session retenue ne redemande que la
    // phrase, et les champs « serveur » et « adresse » n'existent alors pas. Remplir à
    // l'aveugle échouait sur « Bad state: No element », au deuxième passage seulement —
    // le genre de témoin qui passe au vert tant qu'on ne le relance pas.
    if (find.byKey(const Key('champ.serveur')).evaluate().isNotEmpty) {
      await tester.enterText(find.byKey(const Key('champ.serveur')), serveur);
      await tester.enterText(find.byKey(const Key('champ.email')), email);
    }
    await tester.enterText(find.byKey(const Key('champ.phrase')), phrase);
    await tester.pumpAndSettle();
    await tester.testTextInput.receiveAction(TextInputAction.done);

    // La langue enregistrée de la machine décide du premier libellé affiché : on attend
    // donc l'un **ou** l'autre, plutôt que de supposer le français.
    final limite = DateTime.now().add(const Duration(seconds: 40));
    while (find.text('Agenda').evaluate().isEmpty &&
        find.text('Calendar').evaluate().isEmpty) {
      if (DateTime.now().isAfter(limite)) {
        fail(
          'La connexion à $serveur n\'a pas abouti en 40 s. Le banc est-il allumé '
          '(tools/banc-local.sh) ?',
        );
      }
      await tester.pump(const Duration(milliseconds: 250));
      await Future<void>.delayed(const Duration(milliseconds: 250));
    }
    await tester.pumpAndSettle();

    for (final langue in [ChoixDeLangue.francais, ChoixDeLangue.anglais]) {
      for (final theme in [ChoixDeTheme.clair, ChoixDeTheme.sombre]) {
        await apparence.choisirLaLangue(langue);
        await apparence.choisirLeTheme(theme);
        await tester.pumpAndSettle();

        final attendu = theme == ChoixDeTheme.clair ? Brightness.light : Brightness.dark;
        final contexte = tester.element(find.byType(NavigationBar));
        expect(
          Theme.of(contexte).brightness,
          attendu,
          reason: 'Le thème ${theme.name} n\'a pas pris.',
        );

        // Chaque onglet est **touché**, donc construit : une exception dans un écran
        // sombre ne se manifeste qu'à la construction de cet écran-là.
        for (final onglet in onglets[langue]!) {
          expect(
            find.text(onglet),
            findsWidgets,
            reason: 'L\'onglet « $onglet » manque en ${langue.name} : un libellé est '
                'resté en dur, ou la traduction n\'existe pas.',
          );
          await tester.tap(find.text(onglet).first);
          await tester.pumpAndSettle();
        }

        // ── L'agenda, dans ses quatre vues ──
        //
        // La refonte vit ici, et une assertion ne sait pas dire si elle est belle. On
        // traverse donc les quatre vues et on photographie, pour que quelqu'un regarde.
        // Seulement en français : les libellés sont déjà éprouvés dans les deux langues
        // par les onglets ci-dessus, et doubler le jeu doublerait le temps sans rien
        // apprendre de plus sur la mise en page.
        if (langue == ChoixDeLangue.francais) {
          await tester.tap(find.text('Agenda').first);
          await tester.pumpAndSettle();
          for (final vue in ['Jour', 'Semaine', 'Mois', 'Liste']) {
            final bouton = find.text(vue);
            if (bouton.evaluate().isEmpty) {
              fail('La vue « $vue » a disparu du sélecteur : la refonte a changé les '
                  'libellés, et ce témoin ne sait plus ce qu\'il regarde.');
            }
            await tester.tap(bouton.first);
            await tester.pumpAndSettle();
            await photographier(tester, 'agenda-${vue.toLowerCase()}-${theme.name}');
          }
          await tester.tap(find.text('Réglages').first);
          await tester.pumpAndSettle();
        }

        // La section neuve, dans la langue courante : un libellé resté en dur se verrait
        // ici avant de se voir en production.
        //
        // Il faut y descendre : un `ListView` ne construit pas ses enfants hors écran,
        // et chercher le libellé sans défiler ne rend rien — ce qui ressemblerait trait
        // pour trait à une section absente. On tire depuis la ligne « Serveur », dont on
        // sait qu'elle est à l'écran.
        await tester.dragUntilVisible(
          find.byKey(const Key('reglage.rappels')),
          find.byKey(const Key('reglages.serveur')),
          const Offset(0, -200),
        );
        await tester.pumpAndSettle();
        // Le libellé de l'interrupteur, pas l'en-tête de section : `_titre` passe le
        // sien en majuscules, et assertir dessus mesurerait cette transformation autant
        // que la traduction.
        expect(
          find.text(langue == ChoixDeLangue.francais
              ? 'Rappeler mes rendez-vous'
              : 'Remind me of my appointments'),
          findsOneWidget,
          reason: 'La section Rappels doit exister sur iOS, et être traduite.',
        );
        // Éteints par défaut : c'est la promesse, et elle se vérifie à l'œil sur la
        // capture autant qu'ici.
        expect(
          tester.widget<SwitchListTile>(find.byKey(const Key('reglage.rappels'))).value,
          isFalse,
        );

        await photographier(tester, '${langue.name}-${theme.name}');
      }
    }
  }, timeout: const Timeout(Duration(minutes: 8)));
}
