// Searching the agenda on the device: what a query matches.

import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/ecrans/recherche.dart';
import 'package:ghostcal/services/agenda.dart';

LigneDAgenda ligne(String titre, {String? lieu, String? invite}) => LigneDAgenda(
      id: titre,
      evenement: titre,
      debut: DateTime(2026, 10, 20, 9),
      fin: DateTime(2026, 10, 20, 10),
      journeeEntiere: false,
      lectureSeule: false,
      provenance: ProvenanceDuTitre.dechiffre,
      titre: titre,
      lieu: lieu,
      source: invite == null ? 'event' : 'booking',
      invite: invite,
    );

void main() {
  test('accents and case do not matter', () {
    expect(normaliserPourLaRecherche('Réunion Œuvre'), 'reunion oeuvre');
    expect(correspond(ligne('Réunion de lancement'), 'reunion'), isTrue);
    expect(correspond(ligne('reunion'), 'RÉUNION'), isTrue);
  });

  test('every word must match, in the title, the place or the invitee', () {
    expect(correspond(ligne('Atelier', lieu: 'Salle Jura'), 'atelier jura'), isTrue);
    expect(correspond(ligne('Atelier', lieu: 'Salle Jura'), 'atelier leman'), isFalse);
    expect(correspond(ligne('Visio', invite: 'Camille Rossier'), 'rossier'), isTrue);
  });

  test('an empty query matches nothing', () {
    expect(correspond(ligne('Atelier'), '   '), isFalse);
  });
}
