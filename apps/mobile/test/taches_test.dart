// Les règles des tâches qu'aucun vecteur partagé ne peut porter.
//
// L'ordre d'affichage et le retard sont des règles de comportement : elles ne vivent ni
// dans `contrat.json` ni dans le serveur, et elles se cassent en silence. Un témoin par
// règle, comme l'exige l'ADR-0002.

import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/agenda.dart' show ProvenanceDuTitre;
import 'package:ghostcal/services/taches.dart';

Tache tache({
  required String id,
  DateTime? echeance,
  bool faite = false,
  DateTime? creee,
}) =>
    Tache(
      id: id,
      provenance: ProvenanceDuTitre.dechiffre,
      titre: id,
      faite: faite,
      creee: creee ?? DateTime(2026, 1, 1),
      echeance: echeance,
    );

void main() {
  group("L'ordre des tâches", () {
    test('ce qui est fait passe à la fin', () {
      final ordre = Taches.ordonner([
        tache(id: 'faite', faite: true, echeance: DateTime(2026, 1, 1)),
        tache(id: 'à faire', echeance: DateTime(2027, 1, 1)),
      ]).map((t) => t.id).toList();
      // Même avec une échéance bien plus proche : une tâche faite ne presse plus.
      expect(ordre, ['à faire', 'faite']);
    });

    test('les échéances les plus proches viennent en premier', () {
      final ordre = Taches.ordonner([
        tache(id: 'juin', echeance: DateTime(2026, 6, 1)),
        tache(id: 'mars', echeance: DateTime(2026, 3, 1)),
      ]).map((t) => t.id).toList();
      expect(ordre, ['mars', 'juin']);
    });

    test('une tâche sans échéance passe après celles qui en ont une', () {
      // Les mêler par date de création ferait remonter une note vieille de six mois
      // au-dessus d'un rendez-vous de demain.
      final ordre = Taches.ordonner([
        tache(id: 'sans', creee: DateTime(2026, 8, 30)),
        tache(id: 'avec', echeance: DateTime(2027, 1, 1), creee: DateTime(2026, 1, 1)),
      ]).map((t) => t.id).toList();
      expect(ordre, ['avec', 'sans']);
    });

    test('entre deux tâches sans échéance, la plus récente est en haut', () {
      final ordre = Taches.ordonner([
        tache(id: 'ancienne', creee: DateTime(2026, 1, 1)),
        tache(id: 'récente', creee: DateTime(2026, 8, 30)),
      ]).map((t) => t.id).toList();
      expect(ordre, ['récente', 'ancienne']);
    });

    test("l'ordre ne dépend pas de celui d'arrivée", () {
      final entree = [
        tache(id: 'c', faite: true),
        tache(id: 'a', echeance: DateTime(2026, 3, 1)),
        tache(id: 'b', echeance: DateTime(2026, 6, 1)),
      ];
      final premier = Taches.ordonner(entree).map((t) => t.id).toList();
      final second = Taches.ordonner(entree.reversed.toList()).map((t) => t.id).toList();
      expect(premier, second);
      expect(premier, ['a', 'b', 'c']);
    });

    test("ordonner ne modifie pas la liste qu'on lui donne", () {
      // Trier sur place ferait bouger la liste affichée pendant qu'on la parcourt.
      final entree = [tache(id: 'b', echeance: DateTime(2026, 6, 1)), tache(id: 'a')];
      Taches.ordonner(entree);
      expect(entree.map((t) => t.id).toList(), ['b', 'a']);
    });
  });

  group('Le retard', () {
    final maintenant = DateTime(2026, 8, 31, 12);

    test('une échéance dépassée sur une tâche non faite', () {
      expect(tache(id: 'x', echeance: DateTime(2026, 8, 30)).enRetard(maintenant), isTrue);
    });

    test('une tâche faite ne peut pas être en retard', () {
      // Sinon la liste des tâches accomplies se couvrirait d'avertissements rouges.
      expect(
        tache(id: 'x', echeance: DateTime(2026, 8, 30), faite: true).enRetard(maintenant),
        isFalse,
      );
    });

    test('sans échéance, pas de retard', () {
      expect(tache(id: 'x').enRetard(maintenant), isFalse);
    });

    test("une échéance à venir n'est pas un retard", () {
      expect(tache(id: 'x', echeance: DateTime(2026, 9, 1)).enRetard(maintenant), isFalse);
    });
  });
}
