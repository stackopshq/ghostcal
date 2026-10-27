import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/ecrans/ajouter_un_abonnement.dart';
import 'package:ghostcal/ecrans/colonne_laterale.dart';
import 'package:ghostcal/l10n/generated/app_localisations.dart';
import 'package:ghostcal/services/abonnements.dart';
import 'package:ghostcal/services/agenda.dart';
import 'package:ghostcal/theme.dart';

/// Les abonnements à un flux ICS, côté application.
///
/// ─── Le défaut que ces témoins gardent ───
///
/// On pouvait s'abonner à un calendrier depuis le web, et l'application ne savait rien
/// en faire : le mot « subscription » n'apparaissait **nulle part** dans `lib/`. Ni
/// lister, ni ajouter, ni supprimer.
///
/// Ce que ça donnait est pire qu'une absence franche, et c'est ce qui l'a laissé passer
/// si longtemps : le filtre des calendriers est une liste de **masqués** et non une liste
/// d'autorisés, donc les événements du flux s'affichaient quand même. On voyait les
/// rendez-vous d'un abonnement posé depuis le web, dans une couleur qui n'était pas la
/// sienne, sans son nom nulle part, sans sa case pour les cacher, et sans moyen de
/// l'enlever. L'écran était cohérent et faux.
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

  Abonnement abonnement({
    String id = 'a1',
    String nom = 'Jours fériés',
    String couleur = '#2E7DFF',
    String? erreur,
  }) => Abonnement(
    id: id,
    nom: nom,
    url: 'https://exemple.test/$id.ics',
    couleur: couleur,
    bloqueLesDisponibilites: false,
    etat: 'ok',
    derniereErreur: erreur,
  );

  group('la lecture de ce que rend le serveur', () {
    test('un abonnement complet', () {
      final a = Abonnement.depuisJson({
        'id': 'abc',
        'name': 'Ligue 1',
        'url': 'https://exemple.test/l1.ics',
        'color': '#D11F45',
        'blocks_availability': true,
        'status': 'ok',
        'last_error': null,
        'last_synced_at': '2026-10-24T08:30:00Z',
      });
      expect(a.id, 'abc');
      expect(a.nom, 'Ligue 1');
      expect(a.couleur, '#D11F45');
      expect(a.bloqueLesDisponibilites, isTrue);
      expect(a.enPanne, isFalse);
      // Lue en local : une heure UTC affichée telle quelle serait fausse de deux heures
      // en été, et c'est le genre d'écart qu'on ne remarque pas sur une date de synchro.
      expect(
        a.dernierSynchro,
        DateTime.parse('2026-10-24T08:30:00Z').toLocal(),
      );
    });

    test('un flux qui ne répond plus se dit en panne', () {
      expect(abonnement(erreur: '404 Not Found').enPanne, isTrue);
      // Une chaîne vide n'est pas une panne : le serveur rend `null` ou un message, et
      // traiter `''` comme une panne afficherait un avertissement sans cause.
      expect(abonnement(erreur: '').enPanne, isFalse);
      expect(abonnement().enPanne, isFalse);
    });

    test(
      'un champ de date absent ou illisible ne fait pas tomber la liste',
      () {
        // Le reste de l'abonnement vaut mieux que rien : sans cette tolérance, un seul
        // champ mal formé emporterait la liste entière, donc la section de la colonne.
        final a = Abonnement.depuisJson({
          'id': 'x',
          'name': 'X',
          'url': 'https://exemple.test/x.ics',
          'color': '#000000',
          'blocks_availability': false,
          'status': 'ok',
          'last_synced_at': 'pas une date',
        });
        expect(a.dernierSynchro, isNull);
        expect(a.nom, 'X');
      },
    );
  });

  /// La couleur sort de la même palette que les calendriers, et évite celles déjà prises
  /// **des deux côtés**. Une pastille partagée entre un calendrier et un flux ne
  /// relierait plus une ligne colorée de la grille à sa source — ce qui est la seule
  /// chose que cette pastille sert à faire.
  test('un abonnement ne reprend pas la couleur d\'un calendrier', () {
    final prises = ['#2E7DFF', '#15803D'];
    final libre = Agenda.couleurLibre(prises);
    expect(prises, isNot(contains(libre)));
  });

  group('la colonne latérale', () {
    Widget colonne(
      List<Abonnement> abonnements, {
      VoidCallback? surAbonnement,
      ValueChanged<Abonnement>? surDesabonnement,
      Set<String> masques = const {},
      ValueChanged<Set<String>>? surMasques,
    }) => sous(
      ColonneLaterale(
        onglet: 0,
        surOnglet: (_) {},
        calendriers: const [],
        abonnements: abonnements,
        surAbonnement: surAbonnement,
        surDesabonnement: surDesabonnement,
        masques: masques,
        surMasques: surMasques ?? (_) {},
        ancre: DateTime(2026, 10, 24),
        surJour: (_) {},
      ),
    );

    testWidgets('un abonnement porte son nom et sa corbeille', (tester) async {
      Abonnement? supprime;
      await tester.pumpWidget(
        colonne([abonnement()], surDesabonnement: (a) => supprime = a),
      );
      await tester.pump();

      expect(find.text('Jours fériés'), findsOneWidget);
      await tester.tap(find.byKey(const Key('colonne.desabonner.a1')));
      await tester.pump();
      expect(
        supprime?.id,
        'a1',
        reason: 'la corbeille doit rendre l\'abonnement qu\'elle vise',
      );
    });

    /// Le geste que l'application ne savait pas faire. Sans « + » ici, s'abonner
    /// resterait réservé au web — exactement ce qu'on vient de corriger pour la création
    /// d'un calendrier.
    testWidgets('le « + » de la section demande un flux', (tester) async {
      var demande = 0;
      await tester.pumpWidget(
        colonne(const [], surAbonnement: () => demande++),
      );
      await tester.pump();

      expect(
        find.text('ABONNEMENTS'),
        findsOneWidget,
        reason:
            'la section s\'affiche même sans flux, pour pouvoir en ajouter un',
      );

      // Par sa clé propre, et non par l'icône : les deux sections portent un « + », et
      // `_Titre` les distinguait si mal qu'il leur donnait la même clé — c'est ce
      // témoin qui l'a trouvé.
      final bouton = find.byKey(const Key('colonne.nouvel-abonnement'));
      expect(bouton, findsOneWidget);
      expect(
        tester.widget<IconButton>(bouton).tooltip,
        'Nouvel abonnement',
        reason: 'le « + » des flux annonçait qu\'il créait un calendrier',
      );
      await tester.tap(bouton);
      await tester.pump();
      expect(demande, 1);
    });

    /// Vu en capture sur un iPad : sous l'intitulé il n'y avait pas « aucun abonnement »,
    /// il n'y avait **rien**. Honnête, et illisible — ça se lit comme un écran inachevé,
    /// ou comme un chargement qui n'a pas fini. Or n'avoir aucun abonnement est l'état de
    /// la plupart des comptes.
    testWidgets('une section vide le dit, plutôt que de rester vide', (
      tester,
    ) async {
      await tester.pumpWidget(colonne(const [], surAbonnement: () {}));
      await tester.pump();
      expect(find.text('Aucun abonnement'), findsOneWidget);
    });

    testWidgets('et ne le dit plus dès qu\'il y en a un', (tester) async {
      await tester.pumpWidget(colonne([abonnement()], surAbonnement: () {}));
      await tester.pump();
      expect(find.text('Aucun abonnement'), findsNothing);
      expect(find.text('Jours fériés'), findsOneWidget);
    });

    /// Un titre « Abonnements » seul, sans ligne et sans « + », ne dirait rien à qui n'en
    /// a jamais posé — et prendrait de la hauteur à la colonne pour cela.
    testWidgets('et disparaît quand il n\'y a ni flux ni moyen d\'en poser', (
      tester,
    ) async {
      await tester.pumpWidget(colonne(const []));
      await tester.pump();
      expect(find.text('ABONNEMENTS'), findsNothing);
    });

    testWidgets('décocher un abonnement le masque par son identifiant', (
      tester,
    ) async {
      Set<String>? poses;
      await tester.pumpWidget(
        colonne([abonnement()], surMasques: (m) => poses = m),
      );
      await tester.pump();

      await tester.tap(find.byType(Checkbox).last);
      await tester.pump();
      expect(
        poses,
        {'a1'},
        reason:
            'le filtre de la grille porte sur `calendar_id`, et pour un flux le '
            'serveur y met l\'identifiant de l\'abonnement',
      );
    });

    testWidgets('un flux en panne le dit sous son nom', (tester) async {
      await tester.pumpWidget(colonne([abonnement(erreur: '502')]));
      await tester.pump();
      expect(
        find.text('Ce flux ne répond plus'),
        findsOneWidget,
        reason:
            'ce qui s\'affiche vient du dernier rapatriement réussi ; le taire '
            'laisserait croire à un agenda à jour',
      );
    });

    testWidgets('aucune largeur de colonne ne la fait déborder', (
      tester,
    ) async {
      await tester.pumpWidget(
        colonne([
          abonnement(nom: 'Un nom de flux vraiment très long qui ne tient pas'),
          abonnement(id: 'a2', erreur: 'coupé'),
        ], surDesabonnement: (_) {}),
      );
      await tester.pump();
      // Un débordement de rendu ne lève rien : sans cette demande, le témoin passerait
      // sur une colonne visiblement cassée.
      expect(tester.takeException(), isNull);
    });
  });

  group('la boîte qui demande le flux', () {
    Future<FluxDemande?> ouvrir(
      WidgetTester tester, {
      required String nom,
      required String url,
      bool valider = true,
    }) async {
      FluxDemande? rendu;
      await tester.pumpWidget(
        sous(
          Builder(
            builder: (context) => TextButton(
              onPressed: () async =>
                  rendu = await demanderUnAbonnement(context),
              child: const Text('ouvrir'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('ouvrir'));
      await tester.pump();
      await tester.enterText(find.byKey(const Key('abonnement.nom')), nom);
      await tester.enterText(find.byKey(const Key('abonnement.url')), url);
      await tester.tap(
        valider
            ? find.byKey(const Key('abonnement.ajouter'))
            : find.text('Annuler'),
      );
      // Pas de `pumpAndSettle` : le champ porte un curseur clignotant, qui ne se stabilise
      // jamais.
      await tester.pump(const Duration(seconds: 1));
      return rendu;
    }

    testWidgets('rend les deux champs, rognés', (tester) async {
      final r = await ouvrir(
        tester,
        nom: '  Jours fériés  ',
        // L'espace finale d'un copier-coller depuis une feuille de partage est invisible
        // à l'œil et casse l'URL.
        url: ' https://exemple.test/fr.ics ',
      );
      expect(r?.nom, 'Jours fériés');
      expect(r?.url, 'https://exemple.test/fr.ics');
    });

    testWidgets('ne rend rien si un seul des deux champs est rempli', (
      tester,
    ) async {
      expect(await ouvrir(tester, nom: 'Sans adresse', url: ''), isNull);
      expect(
        await ouvrir(tester, nom: '', url: 'https://exemple.test/x.ics'),
        isNull,
      );
    });

    testWidgets('ne rend rien si on annule', (tester) async {
      final r = await ouvrir(
        tester,
        nom: 'Jours fériés',
        url: 'https://exemple.test/fr.ics',
        valider: false,
      );
      expect(r, isNull);
    });

    /// Un lien `webcal://` est ce que donnent Apple, Google et Outlook. Il doit passer
    /// **tel quel** : c'est le serveur qui le réécrit en HTTPS, et le réécrire ici aussi
    /// donnerait deux règles à tenir d'accord.
    testWidgets('un lien webcal:// passe sans être touché', (tester) async {
      final r = await ouvrir(
        tester,
        nom: 'Équipe',
        url: 'webcal://exemple.test/equipe.ics',
      );
      expect(r?.url, 'webcal://exemple.test/equipe.ics');
    });
  });
}
