import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/ecrans/renommer_un_calendrier.dart';
import 'package:ghostcal/l10n/generated/app_localisations.dart';
import 'package:ghostcal/services/agenda.dart';

/// Créer un calendrier : la couleur qu'on lui donne, et le nom qu'on demande.
///
/// La route `POST /v1/me/calendars` existait depuis toujours et l'application ne
/// l'appelait nulle part — créer un calendrier passait obligatoirement par le web. Ces
/// témoins gardent les deux règles que ce chemin ajoute, et aucune ne demande de serveur.
void main() {
  group('la couleur ne se répète pas tant qu\'il en reste', () {
    test('le premier calendrier prend la première teinte', () {
      expect(Agenda.couleurLibre(const []), '#2E7DFF');
    });

    /// Le défaut du serveur vaut `#00f0ff` pour tout le monde. Sans ce choix côté
    /// client, trois calendriers créés d'affilée seraient identiques — et la colonne
    /// latérale, qui colore sa case pour relier une ligne de la grille à son calendrier,
    /// ne relierait plus rien.
    test('elle saute celles qui sont prises', () {
      expect(Agenda.couleurLibre(const ['#2E7DFF']), '#15803D');
      expect(Agenda.couleurLibre(const ['#2E7DFF', '#15803D']), '#D11F45');
    });

    test('la casse du serveur ne la trompe pas', () {
      expect(
        Agenda.couleurLibre(const ['#2e7dff']),
        '#15803D',
        reason: 'le serveur peut rendre la couleur en minuscules',
      );
    });

    /// Au neuvième on recommence, plutôt que d'inventer une teinte dont personne ne sait
    /// ce qu'elle donne sur fond sombre.
    test('passé huit calendriers, elle revient au début', () {
      const huit = [
        '#2E7DFF',
        '#15803D',
        '#D11F45',
        '#B45309',
        '#7C3AED',
        '#0E8FA8',
        '#BE185D',
        '#4D7C0F',
      ];
      expect(Agenda.couleurLibre(huit), '#2E7DFF');
    });
  });

  group('la boîte de création', () {
    Widget sous(Widget enfant) => MaterialApp(
      locale: const Locale('fr'),
      localizationsDelegates: L.localizationsDelegates,
      supportedLocales: L.supportedLocales,
      home: enfant,
    );

    testWidgets('elle demande un nom et le rend détouré', (tester) async {
      String? rendu;
      await tester.pumpWidget(
        sous(
          Builder(
            builder: (context) => TextButton(
              onPressed: () async =>
                  rendu = await demanderUnNomDeCalendrier(context),
              child: const Text('ouvrir'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('ouvrir'));
      await tester.pumpAndSettle();
      expect(find.text('Nouveau calendrier'), findsOneWidget);

      await tester.enterText(
        find.byKey(const Key('calendriers.renommer.champ')),
        '  Perso  ',
      );
      await tester.tap(find.byKey(const Key('calendriers.renommer.valider')));
      await tester.pumpAndSettle();
      expect(
        rendu,
        'Perso',
        reason: 'les espaces autour ne partent pas au serveur',
      );
    });

    testWidgets('un champ vide ne crée rien', (tester) async {
      String? rendu = 'sentinelle';
      await tester.pumpWidget(
        sous(
          Builder(
            builder: (context) => TextButton(
              onPressed: () async =>
                  rendu = await demanderUnNomDeCalendrier(context),
              child: const Text('ouvrir'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('ouvrir'));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('calendriers.renommer.valider')));
      await tester.pumpAndSettle();
      expect(
        rendu,
        isNull,
        reason: 'un calendrier sans nom n\'a pas à exister',
      );
    });

    testWidgets('annuler ne crée rien non plus', (tester) async {
      String? rendu = 'sentinelle';
      await tester.pumpWidget(
        sous(
          Builder(
            builder: (context) => TextButton(
              onPressed: () async =>
                  rendu = await demanderUnNomDeCalendrier(context),
              child: const Text('ouvrir'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('ouvrir'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const Key('calendriers.renommer.champ')),
        'Perso',
      );
      await tester.tap(find.byKey(const Key('calendriers.renommer.annuler')));
      await tester.pumpAndSettle();
      expect(rendu, isNull);
    });
  });
}
