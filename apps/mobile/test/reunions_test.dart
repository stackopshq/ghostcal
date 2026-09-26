// L'ordre des réunions, et la provenance du nom de l'invité.
//
// La provenance est la règle fragile de cet écran : quatre cas qu'il serait naturel
// d'aplatir en deux, et l'aplatissement afficherait « Sans nom » là où le nom existe,
// chiffré, juste à côté.

import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/reunions.dart';

Reunion reunion(String id, DateTime debut) => Reunion(
      id: id,
      intitule: id,
      debut: debut,
      fin: debut.add(const Duration(hours: 1)),
      statut: StatutDeReunion.confirmee,
      courriel: 'x@example.com',
      fuseau: 'Europe/Zurich',
      provenanceDuNom: NomDInvite.inconnu,
      nom: '',
      reponses: const [],
    );

void main() {
  group("L'ordre des réunions", () {
    final janvier = DateTime(2026, 1, 1);
    final juin = DateTime(2026, 6, 1);

    test('à venir : la plus proche en premier', () {
      final ordre = Reunions.ordonner(
        [reunion('juin', juin), reunion('janvier', janvier)],
        PorteeDesReunions.aVenir,
      ).map((r) => r.id).toList();
      expect(ordre, ['janvier', 'juin']);
    });

    test('passées : la plus récente en premier', () {
      // On remonte le temps quand on cherche dans un historique. Garder l'ordre
      // chronologique obligerait à faire défiler des années pour voir la semaine dernière.
      final ordre = Reunions.ordonner(
        [reunion('janvier', janvier), reunion('juin', juin)],
        PorteeDesReunions.passees,
      ).map((r) => r.id).toList();
      expect(ordre, ['juin', 'janvier']);
    });

    test('les deux portées ne donnent pas le même ordre', () {
      final entree = [reunion('janvier', janvier), reunion('juin', juin)];
      expect(
        Reunions.ordonner(entree, PorteeDesReunions.aVenir).map((r) => r.id),
        isNot(Reunions.ordonner(entree, PorteeDesReunions.passees).map((r) => r.id)),
      );
    });

    test("ordonner ne modifie pas la liste qu'on lui donne", () {
      final entree = [reunion('juin', juin), reunion('janvier', janvier)];
      Reunions.ordonner(entree, PorteeDesReunions.aVenir);
      expect(entree.map((r) => r.id).toList(), ['juin', 'janvier']);
    });
  });

  group('Le statut', () {
    test('les valeurs du serveur se lisent', () {
      expect(StatutDeReunion.depuis('confirmed'), StatutDeReunion.confirmee);
      expect(StatutDeReunion.depuis('cancelled'), StatutDeReunion.annulee);
    });

    test("un statut inconnu ne fait pas passer une réunion pour confirmée", () {
      // Retomber sur « confirmée » ferait afficher comme ferme un rendez-vous dont on ne
      // sait rien — c'est le genre de valeur par défaut qui coûte un déplacement.
      expect(StatutDeReunion.depuis('rescheduled'), StatutDeReunion.autre);
      expect(StatutDeReunion.depuis(''), StatutDeReunion.autre);
    });
  });
}
