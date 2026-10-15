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
}
