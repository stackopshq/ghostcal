import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/ecrans/agenda_vues.dart';
import 'package:ghostcal/outils/calendrier.dart';
import 'package:ghostcal/services/agenda.dart';
import 'harnais.dart';

LigneDAgenda ligne(String titre, DateTime debut, int minutes, {bool journee = false}) =>
    LigneDAgenda(
      id: titre,
      evenement: titre,
      debut: debut,
      fin: debut.add(Duration(minutes: minutes)),
      journeeEntiere: journee,
      lectureSeule: false,
      provenance: ProvenanceDuTitre.dechiffre,
      titre: titre,
      source: 'event',
    );

final jour = DateTime(2026, 10, 15);

void main() {
  testWidgets('two simultaneous events are drawn side by side, not stacked',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(400, 900));
    await tester.pumpWidget(appDEpreuve(Scaffold(
      body: GrilleHoraire(
        jours: [jour],
        lignes: [
          ligne('Alpha', DateTime(2026, 10, 15, 9), 60),
          ligne('Beta', DateTime(2026, 10, 15, 9), 60),
        ],
        couleurDe: (_) => Colors.teal,
        surLigne: (_) {},
      ),
    )));
    await tester.pump();
    final a = tester.getRect(find.text('Alpha'));
    final b = tester.getRect(find.text('Beta'));
    expect(a.top, b.top);
    expect(a.left, isNot(b.left), reason: 'they would overlap');
  });

  testWidgets('all-day items go to the strip, not the hour grid', (tester) async {
    await tester.pumpWidget(appDEpreuve(Scaffold(
      body: GrilleHoraire(
        jours: [jour],
        lignes: [ligne('Congé', jour, 24 * 60, journee: true)],
        couleurDe: (_) => Colors.teal,
        surLigne: (_) {},
      ),
    )));
    await tester.pump();
    expect(find.text('Congé'), findsOneWidget);
    expect(tester.getRect(find.text('Congé')).top, lessThan(120));
  });

  testWidgets('tapping an empty slot gives the half hour that was tapped', (tester) async {
    DateTime? choisi;
    await tester.binding.setSurfaceSize(const Size(400, 900));
    await tester.pumpWidget(appDEpreuve(Scaffold(
      body: GrilleHoraire(
        jours: [jour],
        lignes: const [],
        couleurDe: (_) => Colors.teal,
        surLigne: (_) {},
        surCreneau: (d) => choisi = d,
      ),
    )));
    await tester.pump();
    await tester.tapAt(const Offset(250, 300));
    expect(choisi, isNotNull);
    expect(choisi!.minute % 30, 0);
    expect(memeJour(choisi!, jour), isTrue);
  });

  testWidgets('the month grid shows six weeks and marks busy days', (tester) async {
    DateTime? choisi;
    await tester.binding.setSurfaceSize(const Size(400, 900));
    await tester.pumpWidget(appDEpreuve(Scaffold(
      body: GrilleDuMois(
        mois: jour,
        jours: joursDeLaGrilleDuMois(jour, 1),
        selection: jour,
        lignes: [ligne('Alpha', DateTime(2026, 10, 15, 9), 60)],
        couleurDe: (_) => Colors.teal,
        surJour: (d) => choisi = d,
      ),
    )));
    await tester.pump();
    expect(find.byKey(const Key('mois.10.20')), findsOneWidget);
    await tester.tap(find.byKey(const Key('mois.10.20')));
    expect(choisi, DateTime(2026, 10, 20));
  });

  /// ─── La semaine suit la place qu'elle a, pas le nombre de jours qu'elle montre ───
  ///
  /// La règle était « une vue de semaine est étroite », et elle valait tant que la largeur
  /// du contenu était bornée à 560. Dans une fenêtre de Mac la même semaine a deux fois
  /// plus de place, et restait pourtant en caractères de 9,5 points sans ligne d'horaire.
  ///
  /// Ce qui se mesure ici, c'est la **conséquence visible** : l'horaire sous le titre. Il
  /// n'apparaît que dans un bloc assez large, et c'est exactement ce que le seuil décide.
  group('la lisibilité d\'un bloc suit la largeur de son couloir', () {
    final sept = [for (var i = 0; i < 7; i++) plusJours(DateTime(2026, 10, 12), i)];

    Widget semaine() => appDEpreuve(Scaffold(
          body: GrilleHoraire(
            jours: sept,
            lignes: [ligne('Comité de direction', DateTime(2026, 10, 15, 9), 90)],
            couleurDe: (_) => Colors.teal,
            surLigne: (_) {},
          ),
        ));

    testWidgets('une fenêtre de téléphone garde les colonnes muettes', (tester) async {
      await tester.binding.setSurfaceSize(const Size(560, 900));
      await tester.pumpWidget(semaine());
      await tester.pump();
      expect(find.text('Comité de direction'), findsOneWidget);
      expect(find.textContaining('–'), findsNothing,
          reason: '72 points par jour : l\'horaire ne tiendrait pas');
    });

        /// ─── Le débordement de la semaine, frère de celui du mois ───
    ///
    /// Le budget de lignes du titre se calculait sur la hauteur entière du bloc, puis la
    /// ligne d'horaire s'ajoutait par-dessus. Un bloc de 47 points dans un couloir large
    /// débordait de onze. Comme pour la case du mois, `takeException` est la seule façon
    /// de le voir : un débordement est une erreur de rendu, pas une assertion.
    ///
    /// Les durées balayées encadrent le seuil des 34 points où l'horaire paraît, parce
    /// que c'est là que l'oubli se payait.
    testWidgets('aucune largeur ni durée ne fait déborder un bloc', (tester) async {
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final sept = [for (var i = 0; i < 7; i++) plusJours(DateTime(2026, 10, 12), i)];
      // La semaine, parce que c'est là que les couloirs sont étroits sans l'être assez
      // pour basculer en mode compact — l'intervalle où l'oubli se payait. Les largeurs
      // balaient cet intervalle, les durées encadrent le seuil de la ligne d'horaire.
      for (final largeur in [900.0, 1000.0, 1050.0, 1100.0, 1200.0, 1440.0]) {
        for (final minutes in [20, 30, 35, 40, 45, 50, 55, 60, 75, 90]) {
          await tester.binding.setSurfaceSize(Size(largeur, 900));
          await tester.pumpWidget(appDEpreuve(Scaffold(
            body: GrilleHoraire(
              jours: sept,
              lignes: [
                ligne('Comité de direction élargi aux partenaires',
                    DateTime(2026, 10, 15, 9), minutes),
              ],
              couleurDe: (_) => Colors.teal,
              surLigne: (_) {},
            ),
          )));
          await tester.pump();
          expect(tester.takeException(), isNull,
              reason: 'largeur $largeur, bloc de $minutes min');
        }
      }
    });

testWidgets('une fenêtre large rend l\'horaire au bloc', (tester) async {
      await tester.binding.setSurfaceSize(const Size(1100, 900));
      await tester.pumpWidget(semaine());
      await tester.pump();
      expect(find.text('Comité de direction'), findsOneWidget);
      expect(find.textContaining('–'), findsOneWidget);
    });
  });

  /// ─── La grille du mois écrit ce qu'elle peut lire ───
  ///
  /// Les cases valaient 50 points de haut quelle que soit la fenêtre, et ne portaient que
  /// des pastilles. Sur un Mac, la grille occupait le tiers de la hauteur et laissait le
  /// reste vide — et on ne pouvait pas lire son mois sans toucher chaque jour.
  ///
  /// La bascule est une **mesure**, pas une plateforme : c'est la place disponible qui
  /// décide, et c'est pourquoi un téléphone garde ses pastilles sans qu'on ait à le
  /// nommer.
  group('les titres du mois suivent la place', () {
    test('un téléphone n\'a pas la largeur, quelle que soit sa hauteur', () {
      expect(titresParCaseDuMois(const Size(390, 700)), 0);
      expect(titresParCaseDuMois(const Size(390, 2000)), 0,
          reason: '54 points par jour : un titre n\'y serait qu\'une ellipse');
    });

    test('la borne de contenu du téléphone non plus', () {
      expect(titresParCaseDuMois(const Size(560, 900)), 0);
    });

    /// ─── Le seuil, et pourquoi il vaut 135 et non 90 ───
    ///
    /// 720 est la **largeur minimale de la fenêtre macOS**, donc une taille que des gens
    /// auront réellement. Elle donne 101 points par case, soit douze caractères de titre
    /// — « Point hebdom… », « Comité de dire… ». Le premier seuil valait 90 et laissait
    /// passer ça ; mesuré sur le banc, c'était de l'ellipse et pas des titres.
    ///
    /// La bascule tombe donc vers 960 de large, ce qui met le plancher de fenêtre en mode
    /// pastilles — où la grille et la liste du jour se lisent — et garde les titres pour
    /// l'ouverture par défaut, 1100.
    test('le plancher de fenêtre du Mac lit mieux en pastilles', () {
      expect(titresParCaseDuMois(const Size(720, 560)), 0,
          reason: '101 points par case : douze caractères, donc de l\'ellipse');
      expect(titresParCaseDuMois(const Size(950, 800)), 0);
      expect(titresParCaseDuMois(const Size(1000, 800)), greaterThan(0));
      expect(titresParCaseDuMois(const Size(1100, 760)), greaterThan(0),
          reason: 'l\'ouverture par défaut doit garder les titres');
    });

    test('une fenêtre de Mac porte des titres, et plus elle est haute plus il y en a', () {
      final courte = titresParCaseDuMois(const Size(1100, 500));
      final haute = titresParCaseDuMois(const Size(1100, 900));
      expect(courte, greaterThan(0));
      expect(haute, greaterThan(courte));
      expect(titresParCaseDuMois(const Size(1100, 4000)), 5,
          reason: 'bornée : au-delà, une case devient un écran à elle seule');
    });

    testWidgets('en grand, le titre est écrit dans la case', (tester) async {
      await tester.binding.setSurfaceSize(const Size(1100, 800));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(appDEpreuve(Scaffold(
        body: GrilleDuMois(
          mois: jour,
          jours: joursDeLaGrilleDuMois(jour, 1),
          selection: jour,
          lignes: [ligne('Comité de direction', DateTime(2026, 10, 15, 9), 60)],
          couleurDe: (_) => Colors.teal,
          surJour: (_) {},
          titresParCase: titresParCaseDuMois(const Size(1100, 800)),
        ),
      )));
      await tester.pump();
      expect(find.text('Comité de direction'), findsOneWidget);
    });

    testWidgets('en petit, la case reste muette et garde ses pastilles', (tester) async {
      await tester.binding.setSurfaceSize(const Size(390, 700));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(appDEpreuve(Scaffold(
        body: GrilleDuMois(
          mois: jour,
          jours: joursDeLaGrilleDuMois(jour, 1),
          selection: jour,
          lignes: [ligne('Comité de direction', DateTime(2026, 10, 15, 9), 60)],
          couleurDe: (_) => Colors.teal,
          surJour: (_) {},
          titresParCase: titresParCaseDuMois(const Size(390, 700)),
        ),
      )));
      await tester.pump();
      expect(find.text('Comité de direction'), findsNothing,
          reason: 'la liste du jour, sous la grille, le dit à sa place');
    });

    /// ─── Le témoin qui manquait ───
    ///
    /// La première version comptait les titres sur une estimation faite pour la grille
    /// entière, et cette estimation **ignorait la ligne « +N »**. Une case assez remplie
    /// débordait alors de six pixels, c'est-à-dire peignait les barres jaunes et noires
    /// de Flutter en travers du mois. Rien ne le disait tant qu'un jour n'avait pas assez
    /// d'événements pour remplir sa case ; découvert sur le banc après réamorçage.
    ///
    /// `tester.takeException()` est la seule façon de le voir : un débordement est une
    /// erreur de rendu, pas une assertion, et le témoin passait au vert à côté.
    testWidgets('une case trop pleine ne déborde pas', (tester) async {
      await tester.binding.setSurfaceSize(const Size(1100, 800));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(appDEpreuve(Scaffold(
        body: GrilleDuMois(
          mois: jour,
          jours: joursDeLaGrilleDuMois(jour, 1),
          selection: jour,
          // Douze sur le même jour : bien plus que ce qu'une case peut porter.
          lignes: [
            for (var i = 0; i < 12; i++)
              ligne('Rendez-vous $i', DateTime(2026, 10, 15, 8 + i), 30),
          ],
          couleurDe: (_) => Colors.teal,
          surJour: (_) {},
          titresParCase: titresParCaseDuMois(const Size(1100, 800)),
        ),
      )));
      await tester.pump();
      expect(tester.takeException(), isNull,
          reason: 'la case a débordé : les barres jaunes et noires en travers du mois');
      expect(find.textContaining('+'), findsWidgets,
          reason: 'ce qui ne tient pas doit se dire, pas disparaître');
    });

    /// Ce qui ne s'ouvre pas doit se voir **ici aussi** : la grille du mois est souvent le
    /// premier écran qu'on regarde, et y masquer le cas le ferait découvrir ailleurs.
    testWidgets('un contenu illisible garde son mot dans la case', (tester) async {
      await tester.binding.setSurfaceSize(const Size(1100, 800));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(appDEpreuve(Scaffold(
        body: GrilleDuMois(
          mois: jour,
          jours: joursDeLaGrilleDuMois(jour, 1),
          selection: jour,
          lignes: [
            LigneDAgenda(
              id: 'x', evenement: 'x',
              debut: DateTime(2026, 10, 15, 9), fin: DateTime(2026, 10, 15, 10),
              journeeEntiere: false, lectureSeule: false,
              provenance: ProvenanceDuTitre.illisible, titre: '', source: 'event',
            ),
          ],
          couleurDe: (_) => Colors.teal,
          surJour: (_) {},
          titresParCase: titresParCaseDuMois(const Size(1100, 800)),
        ),
      )));
      await tester.pump();
      expect(find.text('Contenu illisible — clé manquante'), findsOneWidget);
    });
  });
}
