// The agenda as a list of days: which tasks go under which day, and how days are named.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/ecrans/agenda_jours.dart';
import 'package:ghostcal/services/agenda.dart';
import 'package:ghostcal/services/taches.dart';

import 'harnais.dart';

Tache tache(String id, DateTime? echeance, {bool faite = false}) => Tache(
  id: id,
  provenance: ProvenanceDuTitre.dechiffre,
  titre: id,
  faite: faite,
  creee: DateTime(2026, 10, 1),
  echeance: echeance,
);

void main() {
  final maintenant = DateTime(2026, 10, 20, 10, 7);

  group('tachesDuJour', () {
    final taches = [
      tache('late', DateTime(2026, 10, 13, 9)),
      tache('today', DateTime(2026, 10, 20, 17)),
      tache('tomorrow', DateTime(2026, 10, 21, 8)),
      tache('done', DateTime(2026, 10, 12), faite: true),
      tache('undated', null),
    ];

    test('today gathers what is due today and everything overdue', () {
      expect(
        tachesDuJour(
          taches,
          DateTime(2026, 10, 20),
          maintenant: maintenant,
        ).map((t) => t.id),
        ['late', 'today'],
      );
    });

    test('another day lists only its own, never done or undated ones', () {
      expect(
        tachesDuJour(
          taches,
          DateTime(2026, 10, 21),
          maintenant: maintenant,
        ).map((t) => t.id),
        ['tomorrow'],
      );
      expect(
        tachesDuJour(
          taches,
          DateTime(2026, 10, 13),
          maintenant: maintenant,
        ).map((t) => t.id),
        ['late'],
      );
    });
  });

  testWidgets('days are named relative to today, empty ones included', (
    tester,
  ) async {
    Tache? cochee;
    await tester.binding.setSurfaceSize(const Size(400, 2000));
    await tester.pumpWidget(
      appDEpreuve(
        Scaffold(
          body: ListeParJour(
            debut: DateTime(2026, 10, 20),
            jours: 3,
            lignes: [
              LigneDAgenda(
                id: 'e1',
                evenement: 'e1',
                debut: DateTime(2026, 10, 22, 9),
                fin: DateTime(2026, 10, 22, 10),
                journeeEntiere: false,
                lectureSeule: false,
                provenance: ProvenanceDuTitre.dechiffre,
                titre: 'Atelier',
                source: 'event',
              ),
            ],
            taches: [tache('late', DateTime(2026, 10, 13, 9))],
            couleurDe: (_) => Colors.teal,
            surLigne: (_) {},
            surTache: (t) => cochee = t,
            maintenant: maintenant,
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.textContaining("AUJOURD'HUI"), findsOneWidget);
    expect(find.textContaining('DEMAIN'), findsOneWidget);
    expect(find.textContaining('JEUDI'), findsOneWidget);
    expect(find.text('Atelier'), findsOneWidget);
    // Overdue under today: its own date is said, in red.
    expect(find.text('13 oct.'), findsOneWidget);

    await tester.tap(find.byKey(const Key('tache.late')));
    expect(cochee?.id, 'late');
  });
}
