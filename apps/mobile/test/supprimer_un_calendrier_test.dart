import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/ecrans/colonne_laterale.dart';
import 'package:ghostcal/l10n/generated/app_localisations.dart';
import 'package:ghostcal/services/agenda.dart';
import 'package:ghostcal/theme.dart';

/// Supprimer un calendrier, côté application.
///
/// ─── Ce que ces témoins gardent ───
///
/// La corbeille ne doit paraître **que** là où le serveur acceptera. Deux calendriers la
/// refusent, pour deux raisons différentes :
///
///   * **le calendrier par défaut** — le serveur répond `409`. Il existe et il est à nous ;
///     ce qui est refusé est ce verbe sur cette ligne. `ensure_default_calendar` en
///     recréerait un à la lecture suivante, donc l'autoriser détruirait les événements pour
///     produire un calendrier vide portant le même rôle ;
///   * **celui de quelqu'un d'autre** — le serveur répond `404`, sa clause `WHERE` portant
///     le propriétaire.
///
/// Un bouton qui échoue **après** la confirmation est pire qu'un bouton absent : on croit
/// avoir supprimé. C'est la même règle que le crayon du renommage, et elle se perd au
/// premier refactoring si rien ne la tient.
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

  Calendrier calendrier({
    String id = 'c1',
    String nom = 'Perso',
    bool parDefaut = false,
    bool partage = false,
  }) => Calendrier(
    id: id,
    nom: nom,
    couleur: '#2E7DFF',
    parDefaut: parDefaut,
    partage: partage,
  );

  Widget colonne(
    List<Calendrier> calendriers, {
    ValueChanged<Calendrier>? surSuppression,
  }) => sous(
    ColonneLaterale(
      onglet: 0,
      surOnglet: (_) {},
      calendriers: calendriers,
      surSuppressionDuCalendrier: surSuppression,
      abonnements: const [],
      masques: const {},
      surMasques: (_) {},
      ancre: DateTime(2026, 10, 27),
      surJour: (_) {},
    ),
  );

  testWidgets('un calendrier à soi porte sa corbeille, et elle rappelle lequel', (
    tester,
  ) async {
    Calendrier? demande;
    await tester.pumpWidget(
      colonne([calendrier()], surSuppression: (c) => demande = c),
    );
    final corbeille = find.byKey(const Key('colonne.supprimer.c1'));
    expect(corbeille, findsOneWidget);

    await tester.tap(corbeille);
    await tester.pump();
    // Le rappel reçoit le calendrier entier et non son seul identifiant : la confirmation
    // doit pouvoir nommer ce qu'elle s'apprête à détruire, et dire s'il est partagé.
    expect(demande?.id, 'c1');
  });

  testWidgets('le calendrier par défaut n\'en porte pas', (tester) async {
    // **Le rappel est fourni.** Sans lui le bouton manquerait de toute façon, et le
    // témoin passerait pour la mauvaise raison — vérifié en retirant la garde
    // `!parDefaut` : il restait vert.
    await tester.pumpWidget(
      colonne([calendrier(parDefaut: true)], surSuppression: (_) {}),
    );
    expect(
      find.byKey(const Key('colonne.supprimer.c1')),
      findsNothing,
      reason: 'le serveur le refuse par un 409 ; le bouton ferait découvrir le refus '
          'après la confirmation, donc après avoir cru supprimer',
    );
  });

  testWidgets('le calendrier d\'un autre n\'en porte pas', (tester) async {
    await tester.pumpWidget(
      colonne([calendrier(partage: true)], surSuppression: (_) {}),
    );
    expect(
      find.byKey(const Key('colonne.supprimer.c1')),
      findsNothing,
      reason: 'le serveur ne trouve pas un calendrier dont on n\'est pas propriétaire',
    );
  });

  testWidgets('sans rappel, aucune corbeille', (tester) async {
    // L'accueil passe `null` tant que l'agenda n'est pas chargé. On ne propose pas un
    // geste définitif sur une liste qu'on n'a pas fini de lire.
    await tester.pumpWidget(colonne([calendrier()]));
    expect(find.byKey(const Key('colonne.supprimer.c1')), findsNothing);
  });

  testWidgets('le crayon et la corbeille cohabitent sans se confondre', (
    tester,
  ) async {
    await tester.pumpWidget(colonne([calendrier()], surSuppression: (_) {}));
    // Les deux boutons existent sur la même ligne. Leurs clés diffèrent, et c'est ce qui
    // empêche un témoin de croire qu'il touche l'un en touchant l'autre.
    expect(find.byKey(const Key('colonne.supprimer.c1')), findsOneWidget);
    expect(find.byIcon(Icons.delete_outline), findsOneWidget);
  });
}
