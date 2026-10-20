// Les témoins des règles que `contrat.json` ne peut pas porter.
//
// L'ADR-0002 le dit : les règles de comportement ne sont pas des vecteurs. Aucune donnée
// partagée ne vérifie qu'un écran distingue « pas authentifié » de « pas déchiffré ».
// Chacune est en revanche témoignable ici — un test qui tombe si la règle est enfreinte.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/ecrans/connexion.dart';
import 'package:ghostcal/services/agenda.dart';
import 'package:ghostcal/services/auth.dart';
import 'package:ghostcal/services/session.dart';
import 'harnais.dart';

Future<void> afficher(WidgetTester tester, Session session) async {
  await tester.pumpWidget(appDEpreuve(EcranDeConnexion(session: session)));
  await tester.pump();
}

void main() {
  group("L'écran de connexion a trois visages", () {
    testWidgets('sans rien d\'enregistré, il demande tout', (tester) async {
      await afficher(tester, Session());
      expect(find.byKey(const Key('champ.serveur')), findsOneWidget);
      expect(find.byKey(const Key('champ.email')), findsOneWidget);
      expect(find.byKey(const Key('champ.phrase')), findsOneWidget);
      expect(find.text('Se connecter'), findsOneWidget);
    });

    testWidgets('une session enregistrée ne redemande que la phrase', (tester) async {
      // Redemander l'adresse et le compte à quelqu'un qui les a déjà donnés est la
      // première friction d'une application qu'on ouvre dix fois par jour.
      final session = Session()
        ..serveur = 'https://ghostcal.example.com'
        ..email = 'clara@example.com';
      session.debugPoserSessionEnregistree(true);
      await afficher(tester, session);
      expect(find.byKey(const Key('champ.serveur')), findsNothing);
      expect(find.byKey(const Key('champ.email')), findsNothing);
      expect(find.byKey(const Key('champ.phrase')), findsOneWidget);
      expect(find.text('Déverrouiller'), findsOneWidget);
      expect(find.textContaining('clara@example.com'), findsOneWidget);
    });

    testWidgets('coffre fermé : on dit que la connexion, elle, a marché', (tester) async {
      // La règle centrale : quelqu'un dont le déverrouillage échoue doit voir qu'il est
      // connecté, et comprendre que c'est sa phrase qui ne va pas. Aplatir les deux états
      // le renverrait à l'écran de connexion sans explication.
      final session = Session()..serveur = 'https://ghostcal.example.com';
      session.debugPoserEtat(Etat.coffreFerme, raison: ErreurDAuth.phraseIncorrecte);
      await afficher(tester, session);
      expect(find.textContaining('Vous êtes connecté'), findsOneWidget);
      expect(find.textContaining("n'ouvre pas le coffre"), findsOneWidget);
      expect(find.byKey(const Key('champ.serveur')), findsNothing);
    });

    // A vault locked by the timer or the lock button is not a failed unlock: claiming
    // the passphrase was wrong, before anything was typed, sent people hunting for a
    // typo that did not exist.
    testWidgets('a merely locked vault does not blame the passphrase', (tester) async {
      final session = Session()..serveur = 'https://ghostcal.example.com';
      session.debugPoserEtat(Etat.coffreFerme);
      await afficher(tester, session);
      expect(find.textContaining('Le coffre est verrouillé'), findsOneWidget);
      expect(find.textContaining("n'ouvre pas le coffre"), findsNothing);
    });

    testWidgets('la récupération ne se propose pas à la connexion', (tester) async {
      // À la connexion, c'est le mot de passe du compte qu'on tape : une phrase de
      // récupération n'y ouvrirait rien, et la proposer enverrait chercher à côté.
      await afficher(tester, Session());
      expect(find.text('Utiliser ma phrase de récupération'), findsNothing);

      final session = Session()..serveur = 'https://ghostcal.example.com';
      session.debugPoserEtat(Etat.coffreFerme);
      await afficher(tester, session);
      expect(find.text('Utiliser ma phrase de récupération'), findsOneWidget);
    });
  });

  group("L'heure envoyée au serveur", () {
    test('porte toujours un fuseau', () {
      // `toIso8601String` d'une date locale n'en porte aucun : le serveur la lirait comme
      // de l'UTC, et tout l'agenda glisserait du décalage horaire — sans erreur, juste
      // faux. C'est exactement la classe de défaut que l'ADR-0002 combat.
      final iso = Agenda.isoPourLeServeur(DateTime(2026, 6, 1, 14, 30));
      expect(iso.endsWith('Z'), isTrue, reason: iso);
    });

    test("le même instant s'écrit pareil quel que soit le fuseau de départ", () {
      final local = DateTime.fromMillisecondsSinceEpoch(1788000000000);
      expect(
        Agenda.isoPourLeServeur(local),
        Agenda.isoPourLeServeur(local.toUtc()),
      );
    });
  });

  // Le premier écran, dans la langue de l'appareil.
  //
  // « Serveur » était écrit en dur à côté de trois libellés traduits : sur une interface
  // anglaise, le premier champ du premier écran s'affichait en français. Relevé en
  // photographiant le simulateur, pas en relisant — « EMAIL ADDRESS », « MASTER PASSWORD »,
  // « Sign in », et « SERVEUR » au milieu.
  //
  // C'est l'écran que voit l'examinateur d'Apple avant tout autre.
  testWidgets('le libellé du serveur suit la langue', (tester) async {
    for (final (locale, attendu, absent) in [
      // En majuscules : `_libelle` passe le titre par `toUpperCase()`. Assertir sur la
      // casse d'origine mesurerait cette transformation autant que la traduction, et
      // c'est ce qui a fait rougir la première version de ce témoin.
      (const Locale('en'), 'SERVER', 'SERVEUR'),
      (const Locale('fr'), 'SERVEUR', 'SERVER'),
    ]) {
      await tester.pumpWidget(appDEpreuve(
        EcranDeConnexion(session: Session()),
        locale: locale,
      ));
      await tester.pump();
      expect(find.text(attendu), findsWidgets,
          reason: 'en ${locale.languageCode}, le champ doit dire « $attendu »');
      expect(find.text(absent), findsNothing,
          reason: 'en ${locale.languageCode}, « $absent » n\'a rien à faire là');
    }
  });
}
