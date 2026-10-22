// Renommer un calendrier : ce qui part sur le réseau, et ce qui n'en part pas.
//
// Le défaut d'origine se voyait en devanture : le serveur nomme le calendrier par défaut
// « Mon agenda » pour tout le monde, et `PATCH /v1/me/calendars/{id}` ne prenait qu'une
// couleur. Un anglophone restait donc avec un nom français qu'il ne pouvait pas changer,
// et la capture App Store anglaise l'affichait.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/ecrans/renommer_un_calendrier.dart';
import 'package:ghostcal/services/agenda.dart';
import 'package:ghostcal/services/api.dart';
import 'package:ghostcal/services/auth.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'harnais.dart';

Calendrier calendrier({
  String id = 'c1',
  String nom = 'Mon agenda',
  bool partage = false,
  bool? peutEcrire,
}) => Calendrier(
  id: id,
  nom: nom,
  couleur: '#00f0ff',
  parDefaut: true,
  partage: partage,
  peutEcrireBrut: peutEcrire,
);

void main() {
  group('la requête', () {
    late List<http.Request> recues;

    Agenda agenda({int statut = 204, String corps = ''}) {
      recues = [];
      final api = ClientAPI(
        base: Uri.parse('https://cal.example.com'),
        client: MockClient((r) async {
          recues.add(r);
          return http.Response(corps, statut);
        }),
      );
      return Agenda(api: api, auth: Auth(api));
    }

    test('part en PATCH sur le calendrier nommé', () async {
      final a = agenda();
      await a.renommerLeCalendrier(id: 'c1', nom: 'Perso');
      expect(recues, hasLength(1));
      expect(recues.single.method, 'PATCH');
      expect(recues.single.url.path, '/v1/me/calendars/c1');
    });

    test("ne porte que le nom : la couleur n'est pas renvoyée", () async {
      // C'est la raison d'être du PATCH. Un PUT obligerait à réémettre la couleur, donc à
      // l'avoir lue ; un client qui ne l'aurait pas lue la remettrait à sa valeur par
      // défaut sans erreur. GhostCal a déjà payé cette distinction une fois, sur les types
      // de rendez-vous, où un PUT amputé d'un champ le réinitialisait en silence.
      final a = agenda();
      await a.renommerLeCalendrier(id: 'c1', nom: 'Perso');
      expect(jsonDecode(recues.single.body), {'name': 'Perso'});
    });

    test('le nom est rogné avant de partir', () async {
      // Sans cela, « Perso » suivi d'une espace partirait, le serveur le rognerait, et
      // l'écran afficherait au rechargement autre chose que ce qui a été tapé. L'écart
      // est muet : aucune erreur, juste un nom qui n'est pas celui qu'on croit.
      final a = agenda();
      await a.renommerLeCalendrier(id: 'c1', nom: '  Perso  ');
      expect(jsonDecode(recues.single.body), {'name': 'Perso'});
    });

    test('un refus du serveur remonte, il ne se tait pas', () async {
      // Un nom vide est un 422 côté serveur. S'il était avalé ici, l'écran reposerait le
      // nouveau nom en mémoire et montrerait un renommage qui n'a pas eu lieu.
      final a = agenda(statut: 422, corps: '{"detail":"name must not be blank"}');
      await expectLater(
        a.renommerLeCalendrier(id: 'c1', nom: 'x'),
        throwsA(isA<Object>()),
      );
    });
  });

  group('qui porte un crayon', () {
    test('un calendrier à soi, oui', () {
      expect(calendrier().aSoi, isTrue);
    });

    test('un calendrier partagé par quelqu’un d’autre, non', () {
      // Et ce n'est pas la même question que le droit d'écriture : on peut vous laisser
      // écrire dans son calendrier sans vous laisser le rebaptiser chez lui. Le serveur
      // le refuserait — sa clause WHERE porte le propriétaire — et il rendrait un 404.
      // Proposer le geste serait promettre ce qui ne sera pas tenu.
      expect(calendrier(partage: true, peutEcrire: true).aSoi, isFalse);
      expect(calendrier(partage: true, peutEcrire: true).inscriptible, isTrue);
    });
  });

  group('la copie renommée', () {
    test('ne change que le nom', () {
      final avant = Calendrier(
        id: 'c1',
        nom: 'Mon agenda',
        couleur: '#ff0066',
        parDefaut: true,
        partage: false,
        proprietaire: 'Clara',
        peutEcrireBrut: false,
      );
      final apres = avant.renomme('Perso');
      expect(apres.nom, 'Perso');
      expect(apres.id, avant.id);
      expect(apres.couleur, avant.couleur);
      expect(apres.parDefaut, avant.parDefaut);
      expect(apres.partage, avant.partage);
      expect(apres.proprietaire, avant.proprietaire);
      // `peutEcrireBrut` à `false` et non `null` : le recopier tel quel importe, parce que
      // `inscriptible` retombe sur « oui » quand il est absent. Le perdre rendrait
      // inscriptible un calendrier en lecture seule, et l'enregistrement échouerait une
      // fois l'événement entièrement saisi.
      expect(apres.peutEcrireBrut, isFalse);
      expect(apres.inscriptible, isFalse);
    });
  });

  group('la boîte de renommage', () {
    // Ce que la boîte rend, c'est ce qui partira sur le réseau — ou rien. Les trois cas
    // qui doivent rendre `null` sont des cas où un PATCH réussirait sans rien changer.
    late String? rendu;
    late int ouvertures;

    Future<void> ouvrir(WidgetTester tester, {String nomActuel = 'Mon agenda'}) async {
      rendu = 'pas encore appelée';
      ouvertures = 0;
      await tester.pumpWidget(appDEpreuve(
        Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: ElevatedButton(
                onPressed: () async {
                  ouvertures++;
                  rendu = await demanderUnNouveauNom(
                    context,
                    nomActuel: nomActuel,
                  );
                },
                child: const Text('ouvrir'),
              ),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('ouvrir'));
      await tester.pumpAndSettle();
      expect(ouvertures, 1);
    }

    testWidgets('le champ arrive rempli du nom courant', (tester) async {
      await ouvrir(tester);
      final champ = tester.widget<TextField>(
        find.byKey(const Key('calendriers.renommer.champ')),
      );
      expect(champ.controller?.text, 'Mon agenda');
    });

    testWidgets('un nom changé est rendu, rogné', (tester) async {
      await ouvrir(tester);
      await tester.enterText(
        find.byKey(const Key('calendriers.renommer.champ')),
        '  Perso  ',
      );
      await tester.tap(find.byKey(const Key('calendriers.renommer.valider')));
      await tester.pumpAndSettle();
      expect(rendu, 'Perso');
    });

    testWidgets('annuler ne rend rien', (tester) async {
      await ouvrir(tester);
      await tester.enterText(
        find.byKey(const Key('calendriers.renommer.champ')),
        'Perso',
      );
      await tester.tap(find.byKey(const Key('calendriers.renommer.annuler')));
      await tester.pumpAndSettle();
      expect(rendu, isNull, reason: 'un nom saisi puis annulé ne part pas');
    });

    testWidgets('un champ vidé ne rend rien', (tester) async {
      // Le serveur rendrait 422. Le demander serait une erreur qu'on s'inflige : la boîte
      // sait déjà qu'un nom vide n'est pas un nom.
      await ouvrir(tester);
      await tester.enterText(
        find.byKey(const Key('calendriers.renommer.champ')),
        '   ',
      );
      await tester.tap(find.byKey(const Key('calendriers.renommer.valider')));
      await tester.pumpAndSettle();
      expect(rendu, isNull);
    });

    testWidgets('le même nom ne rend rien', (tester) async {
      // Le cas le plus fréquent : on ouvre, on regarde, on valide.
      await ouvrir(tester);
      await tester.tap(find.byKey(const Key('calendriers.renommer.valider')));
      await tester.pumpAndSettle();
      expect(rendu, isNull);
    });

    testWidgets('Entrée vaut validation', (tester) async {
      await ouvrir(tester);
      await tester.enterText(
        find.byKey(const Key('calendriers.renommer.champ')),
        'Perso',
      );
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pumpAndSettle();
      expect(rendu, 'Perso');
    });

    testWidgets('la boîte parle anglais quand l’application le fait', (tester) async {
      // Le défaut d'origine est un défaut de langue : c'est la dernière chose à laisser
      // au hasard sur l'écran qui le répare.
      await tester.pumpWidget(appDEpreuve(
        Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: ElevatedButton(
                onPressed: () =>
                    demanderUnNouveauNom(context, nomActuel: 'My calendar'),
                child: const Text('ouvrir'),
              ),
            ),
          ),
        ),
        locale: const Locale('en'),
      ));
      await tester.tap(find.text('ouvrir'));
      await tester.pumpAndSettle();
      expect(find.text('Rename calendar'), findsOneWidget);
      expect(find.text('Save'), findsOneWidget);
    });
  });
}
