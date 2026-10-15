// All-day events: stored like the web stores them, shown at the head of their day.
// On a device, an event switched to "all day" kept its 15:00–16:00 hours and was listed
// after the afternoon's meetings.

import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/agenda.dart';

LigneDAgenda ligne(String id, DateTime debut, {bool journee = false}) => LigneDAgenda(
      id: id,
      evenement: id,
      debut: debut,
      fin: debut.add(const Duration(hours: 1)),
      journeeEntiere: journee,
      lectureSeule: false,
      provenance: ProvenanceDuTitre.dechiffre,
      titre: id,
      source: 'event',
    );

void main() {
  group('bornesDeJournee', () {
    test('a single day becomes midnight to the next midnight', () {
      final b = Agenda.bornesDeJournee(
          DateTime(2026, 10, 15, 15), DateTime(2026, 10, 15, 16));
      expect(b.debut, DateTime(2026, 10, 15));
      expect(b.fin, DateTime(2026, 10, 16));
    });

    test('several days end the midnight after the last day', () {
      final b = Agenda.bornesDeJournee(DateTime(2026, 10, 15, 9), DateTime(2026, 10, 17, 9));
      expect(b.debut, DateTime(2026, 10, 15));
      expect(b.fin, DateTime(2026, 10, 18));
    });

    test('an end before the start still gives one whole day', () {
      final b = Agenda.bornesDeJournee(DateTime(2026, 10, 15), DateTime(2026, 10, 14));
      expect(b.fin, DateTime(2026, 10, 16));
    });

    test('crosses a month end', () {
      final b = Agenda.bornesDeJournee(DateTime(2026, 10, 31, 8), DateTime(2026, 10, 31, 9));
      expect(b.fin, DateTime(2026, 11, 1));
    });
  });

  group('dernierJourInclus', () {
    test('shows the last day, not the exclusive midnight', () {
      expect(Agenda.dernierJourInclus(DateTime(2026, 10, 15), DateTime(2026, 10, 16)),
          DateTime(2026, 10, 15));
    });

    test('an end that is not midnight is left alone (legacy rows)', () {
      final fin = DateTime(2026, 10, 15, 16);
      expect(Agenda.dernierJourInclus(DateTime(2026, 10, 15, 15), fin), fin);
    });

    test('round-trips with bornesDeJournee', () {
      final b = Agenda.bornesDeJournee(DateTime(2026, 10, 15), DateTime(2026, 10, 17));
      expect(Agenda.dernierJourInclus(b.debut, b.fin), DateTime(2026, 10, 17));
    });
  });

  test('all-day items head their day, then by start time', () {
    final lignes = [
      ligne('reunion', DateTime(2026, 10, 15, 9)),
      ligne('journee', DateTime(2026, 10, 15, 15), journee: true),
      ligne('matin', DateTime(2026, 10, 15, 8)),
    ]..sort(Agenda.comparerLesLignes);
    expect(lignes.map((l) => l.id), ['journee', 'matin', 'reunion']);
  });
}
