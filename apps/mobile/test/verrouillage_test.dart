// Le verrouillage automatique, et le cadenas qui va avec.
//
// La règle est simple et ses défaillances sont muettes : un coffre qui ne se referme pas
// reste ouvert, et rien ne le dit. C'est exactement le genre de fonction qu'on croit
// acquise parce qu'elle n'a jamais protesté.

import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/verrouillage.dart';

void main() {
  final parti = DateTime(2026, 8, 31, 22, 0);

  group('Faut-il refermer ?', () {
    test('« immédiatement » referme même après une seconde', () {
      expect(
        Verrouillage.refermeApres(DelaiDeVerrouillage.immediat,
            depuis: parti, maintenant: parti.add(const Duration(seconds: 1))),
        isTrue,
      );
    });

    test('un délai réglé laisse le coffre ouvert avant son terme', () {
      expect(
        Verrouillage.refermeApres(DelaiDeVerrouillage.cinqMinutes,
            depuis: parti,
            maintenant: parti.add(const Duration(minutes: 4, seconds: 59))),
        isFalse,
      );
    });

    test('et referme à son terme exact', () {
      // La borne est incluse : à cinq minutes pile, on referme. Un « strictement après »
      // laisserait le coffre ouvert une seconde de plus pour rien.
      expect(
        Verrouillage.refermeApres(DelaiDeVerrouillage.cinqMinutes,
            depuis: parti, maintenant: parti.add(const Duration(minutes: 5))),
        isTrue,
      );
    });

    test('les quatre choix ne se valent pas', () {
      // Contrôle négatif : sans lui, une implémentation qui refermerait toujours passerait
      // les tests précédents sauf un.
      final apres = parti.add(const Duration(minutes: 10));
      expect(
        [
          for (final choix in DelaiDeVerrouillage.values)
            Verrouillage.refermeApres(choix, depuis: parti, maintenant: apres),
        ],
        // Immédiat, 1 min et 5 min referment ; 15 min non.
        [true, true, true, false],
      );
    });
  });

  group('Le cadenas', () {
    test("ne s'affiche pas quand le verrouillage est immédiat", () {
      // Il ferait doublon avec ce que le système fait seul en quittant l'application, et
      // prendrait la meilleure place de la barre pour rien.
      expect(Verrouillage.cadenasVisiblePour(DelaiDeVerrouillage.immediat), isFalse);
    });

    test("s'affiche dès qu'un délai est réglé", () {
      for (final choix in DelaiDeVerrouillage.values.where((c) => c.delai != null)) {
        expect(Verrouillage.cadenasVisiblePour(choix), isTrue, reason: choix.name);
      }
    });
  });

  group('Le réglage retenu', () {
    test('un nom inconnu retombe sur le choix sûr, pas sur le plus permissif', () {
      // Une version plus récente pourrait écrire une valeur que celle-ci ignore. Retomber
      // sur « quinze minutes » laisserait le coffre ouvert par ignorance.
      expect(
        DelaiDeVerrouillage.values
            .firstWhere((v) => v.name == 'uneJournee',
                orElse: () => DelaiDeVerrouillage.immediat),
        DelaiDeVerrouillage.immediat,
      );
    });

    test('« immédiat » veut dire tout de suite, pas jamais', () {
      // Un délai nul lu comme « pas de verrouillage » ouvrirait le coffre en grand. La
      // distinction est portée par `doitVerrouiller`, pas par le nul lui-même.
      expect(DelaiDeVerrouillage.immediat.delai, isNull);
      expect(
        Verrouillage.refermeApres(DelaiDeVerrouillage.immediat,
            depuis: parti, maintenant: parti),
        isTrue,
      );
    });
  });
}
