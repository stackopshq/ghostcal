import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/ecrans/colonne_laterale.dart';
import 'package:ghostcal/l10n/generated/app_localisations.dart';
import 'package:ghostcal/services/api.dart';
import 'package:ghostcal/services/connexions.dart';
import 'package:ghostcal/theme.dart';

/// Les comptes externes connectés — CalDAV, iCloud, Google — côté application.
///
/// ─── Le défaut que ces témoins gardent ───
///
/// `git log -S "calendar/connections"` sur `apps/mobile/` ne rendait **pas un seul
/// commit** : aucune version du client, sur aucune plateforme, n'a jamais appelé cette
/// route. Et comme le filtre de l'agenda est une liste de masqués et non d'autorisés,
/// les créneaux de ces comptes s'affichaient quand même — dans la couleur d'accent faute
/// de correspondance, sans nom et sans case pour les cacher.
///
/// C'est exactement le défaut que les abonnements ICS ont eu jusqu'en 1.8.0, à ceci près
/// qu'il a duré plus longtemps et qu'il touche la source la plus fournie des trois : un
/// agenda professionnel remplit une semaine, un flux de jours fériés y met un jour.
///
/// Un client l'a signalé le 2026-11-03, dans ces termes : « dans cal macOS je ne vois pas
/// mes calendriers externes ».
void main() {
  Widget sous(Widget enfant) => MaterialApp(
    locale: const Locale('fr'),
    localizationsDelegates: const [
      ...L.localizationsDelegates,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
    ],
    supportedLocales: L.supportedLocales,
    theme: themeGhostcal(Brightness.light),
    home: Scaffold(body: enfant),
  );

  Connexion connexion({
    String id = 'c1',
    String? nom = 'Travail',
    String couleur = '#2E7DFF',
    String etat = 'active',
    String identifiant = 'clara@exemple.test',
  }) => Connexion(
    id: id,
    serveur: 'https://dav.exemple.test/',
    identifiant: identifiant,
    couleur: couleur,
    etat: etat,
    nomDuCalendrier: nom,
  );

  group('la lecture de ce que rend le serveur', () {
    test('une connexion complète', () {
      final c = Connexion.depuisJson({
        'id': 'abc',
        'server_url': 'https://caldav.icloud.com/',
        'username': 'clara@exemple.test',
        'calendar_name': 'Perso',
        'color': '#D11F45',
        'mirror_bookings': true,
        'mirror_detail': 'busy',
        'status': 'active',
        'last_synced_at': '2026-11-03T08:30:00Z',
      });
      expect(c.id, 'abc');
      expect(c.libelle, 'Perso');
      expect(c.couleur, '#D11F45');
      expect(c.enPanne, isFalse);
      // Lue en local : une heure UTC affichée telle quelle serait fausse de deux heures
      // en été, ce qui ne se voit pas tant qu'on ne regarde pas l'heure de près.
      expect(c.dernierSynchro, DateTime.utc(2026, 11, 3, 8, 30).toLocal());
    });

    test('aucun mot de passe ne figure dans ce que le modèle retient', () {
      // Le serveur n'en rend pas, et le modèle n'a pas de champ pour en loger un. Le
      // témoin garde l'absence : un champ ajouté « au cas où » finirait par être rempli,
      // puis journalisé.
      final c = Connexion.depuisJson({
        'id': 'abc',
        'server_url': 'https://dav.exemple.test/',
        'username': 'clara',
        'calendar_name': null,
        'color': '#000000',
        'status': 'active',
        'password': 'ne-devrait-jamais-arriver',
      });
      expect(c.toString(), isNot(contains('ne-devrait-jamais-arriver')));
    });
  });

  group('le service, contre un serveur simulé', () {
    Connexions service(MockClient client) => Connexions(
      api: ClientAPI(base: Uri.parse('https://cal.exemple.test'), client: client),
    );

    test('la liste part sur la bonne route et se lit', () async {
      late http.Request recue;
      final liste = await service(MockClient((r) async {
        recue = r;
        return http.Response(
          jsonEncode([
            {
              'id': 'c1',
              'server_url': 'https://dav.exemple.test/',
              'username': 'clara',
              'calendar_name': 'Travail',
              'color': '#2E7DFF',
              'status': 'active',
            },
          ]),
          200,
        );
      })).lister();
      expect(recue.method, 'GET');
      expect(recue.url.path, '/v1/me/calendar/connections');
      expect(liste.single.libelle, 'Travail');
    });

    test('un serveur en panne lève, il ne rend pas une liste vide', () async {
      // La distinction décide de ce que voit l'utilisateur. Une liste vide rendue en
      // silence ferait disparaître la section, donc disparaître des comptes qui
      // existent — un écran cohérent et faux, exactement le défaut qu'on corrige ici.
      // En levant, c'est l'écran qui décide, et il garde la dernière liste connue.
      await expectLater(
        service(MockClient((_) async => http.Response('nope', 500))).lister(),
        throwsA(anything),
      );
    });

    test('la synchronisation rend le nombre de comptes qui ont abouti', () async {
      late http.Request recue;
      final combien = await service(MockClient((r) async {
        recue = r;
        return http.Response('{"synced": 2}', 200);
      })).synchroniser();
      expect(recue.method, 'POST');
      expect(recue.url.path, '/v1/me/calendar/sync');
      // Les mains vides : la route ne lit aucune charge, et lui en envoyer une
      // obligerait le serveur à l'accepter pour toujours.
      expect(recue.body, isEmpty);
      expect(combien, 2);
    });

    test('zéro compte synchronisé se lit comme zéro, pas comme une absence', () async {
      final combien = await service(
        MockClient((_) async => http.Response('{"synced": 0}', 200)),
      ).synchroniser();
      expect(combien, 0);
    });
  });

  group('le libellé, qui ne doit jamais être vide', () {
    test('le nom du calendrier distant quand il y en a un', () {
      expect(connexion(nom: 'Travail').libelle, 'Travail');
    });

    test('sinon le compte : un serveur CalDAV n\'est pas tenu de nommer', () {
      expect(connexion(nom: null).libelle, 'clara@exemple.test');
      expect(connexion(nom: '   ').libelle, 'clara@exemple.test');
    });

    test('sinon l\'hôte du serveur, plutôt qu\'une case muette', () {
      expect(connexion(nom: null, identifiant: '').libelle, 'dav.exemple.test');
    });
  });

  group('la panne', () {
    test('« active » va bien, « needs_reauth » se signale', () {
      // Les deux seules valeurs que la base autorise :
      // CheckConstraint("status IN ('active', 'needs_reauth')").
      expect(connexion(etat: 'active').enPanne, isFalse);
      expect(connexion(etat: 'needs_reauth').enPanne, isTrue);
    });

    test('un état que le serveur inventerait se signale aussi', () {
      // Se tromper dans ce sens fait regarder un compte qui va bien ; dans l'autre, il
      // fait rater un agenda figé depuis des semaines.
      expect(connexion(etat: 'ce-que-le-serveur-inventera').enPanne, isTrue);
    });
  });

  group('la colonne latérale', () {
    Widget colonne(
      List<Connexion> connexions, {
      Set<String> masques = const {},
      ValueChanged<Set<String>>? surMasques,
      Future<void> Function()? surSynchronisation,
    }) => sous(
      ColonneLaterale(
        onglet: 0,
        surOnglet: (_) {},
        calendriers: const [],
        abonnements: const [],
        connexions: connexions,
        surSynchronisation: surSynchronisation,
        masques: masques,
        surMasques: surMasques ?? (_) {},
        ancre: DateTime(2026, 11, 3),
        surJour: (_) {},
      ),
    );

    testWidgets('un compte connecté porte son nom', (tester) async {
      await tester.pumpWidget(colonne([connexion()]));
      expect(find.text('Comptes connectés'.toUpperCase()), findsOneWidget);
      expect(find.text('Travail'), findsOneWidget);
    });

    testWidgets('décocher un compte le masque par son identifiant', (
      tester,
    ) async {
      Set<String>? poses;
      await tester.pumpWidget(
        colonne([connexion(id: 'c9')], surMasques: (m) => poses = m),
      );
      await tester.tap(find.byKey(const Key('colonne.compte.c9')));
      await tester.pumpAndSettle();
      // L'identifiant de la connexion, et non un autre : c'est lui que le serveur met
      // dans `calendar_id` des lignes `source: "external"`, donc lui que le filtre de
      // l'agenda compare. Un identifiant voisin masquerait silencieusement rien.
      expect(poses, {'c9'});
    });

    testWidgets('un compte en panne le dit sous son nom', (tester) async {
      await tester.pumpWidget(colonne([connexion(etat: 'needs_reauth')]));
      expect(find.text('À reconnecter depuis le web'), findsOneWidget);
    });

    testWidgets('aucune section quand il n\'y a aucun compte', (tester) async {
      // La différence avec les abonnements, qui affichent « Aucun abonnement » : on ne
      // peut pas connecter un compte depuis cet écran, donc un intitulé vide
      // n'offrirait aucun geste et n'apprendrait rien.
      await tester.pumpWidget(colonne(const [], surSynchronisation: () async {}));
      expect(find.text('Comptes connectés'.toUpperCase()), findsNothing);
      expect(find.byKey(const Key('colonne.synchroniser')), findsNothing);
    });

    testWidgets('le bouton redemande les comptes au serveur', (tester) async {
      var demande = 0;
      await tester.pumpWidget(
        colonne([connexion()], surSynchronisation: () async => demande++),
      );
      await tester.tap(find.byKey(const Key('colonne.synchroniser')));
      await tester.pumpAndSettle();
      expect(demande, 1);
    });

    testWidgets('sans moyen de synchroniser, pas de bouton mort', (
      tester,
    ) async {
      await tester.pumpWidget(colonne([connexion()]));
      expect(find.text('Travail'), findsOneWidget);
      expect(find.byKey(const Key('colonne.synchroniser')), findsNothing);
    });
  });
}
