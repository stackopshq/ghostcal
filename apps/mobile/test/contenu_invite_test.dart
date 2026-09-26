import 'package:flutter_test/flutter_test.dart';

import 'package:ghostcal/modeles/contenus.dart';

/// « Absent » n'est pas « illisible », et l'écran des réunions le disait mal.
///
/// Le bloc `invitee_private` est scellé à l'organisation : le serveur le stocke sans
/// pouvoir l'ouvrir, et l'application le déchiffre. Trois issues existent, pas deux :
///
///   · le sceau s'ouvre et le contenu se lit      → on affiche le nom ;
///   · le sceau s'ouvre, mais un champ manque     → on affiche ce qu'on a ;
///   · le sceau ne s'ouvre pas                    → « illisible », en rouge.
///
/// La deuxième ligne manquait. `depuisJson` exigeait `name`, `notes` **et** `answers` ;
/// une réservation sans notes — le cas ordinaire d'un invité qui n'écrit rien — rendait
/// `null`, et l'écran annonçait « nom illisible » à côté d'une adresse parfaitement
/// lisible. Le sceau s'était pourtant ouvert sans peine.
///
/// Le défaut a été vu sur une capture d'écran App Store, pas ici : les tests passaient
/// tous, parce qu'ils fournissaient toujours les trois champs.
void main() {
  group('ce qui doit se lire', () {
    test('le cas complet', () {
      final c = ContenuDInvite.depuisJson(
        '{"name":"Camille Rossier","answers":{"sujet":"Refonte"},"notes":"A midi"}',
      );
      expect(c, isNotNull);
      expect(c!.name, 'Camille Rossier');
      expect(c.notes, 'A midi');
      expect(c.answers['sujet'], 'Refonte');
    });

    test('sans notes, le cas qui affichait « illisible »', () {
      final c = ContenuDInvite.depuisJson(
        '{"name":"Antoine Beguin","answers":{"sujet":"Migration"}}',
      );
      expect(c, isNotNull,
          reason: "Un invité qui n'écrit pas de note reste parfaitement lisible.");
      expect(c!.name, 'Antoine Beguin');
      expect(c.notes, isEmpty);
    });

    test('sans réponses', () {
      final c = ContenuDInvite.depuisJson('{"name":"Salome Vuillemin"}');
      expect(c, isNotNull);
      expect(c!.name, 'Salome Vuillemin');
      expect(c.answers, isEmpty);
    });

    test('sans nom : les réponses restent lisibles', () {
      // Le nom vide est traité plus haut, par `NomDInvite.inconnu` — « inconnu » et
      // « illisible » sont deux états distincts, et c'est tout l'objet de ce fichier.
      final c = ContenuDInvite.depuisJson('{"answers":{"sujet":"Budget"}}');
      expect(c, isNotNull);
      expect(c!.name, isEmpty);
      expect(c.answers['sujet'], 'Budget');
    });
  });

  group('ce qui doit rester refusé', () {
    // La tolérance porte sur des **champs facultatifs**, jamais sur la forme du document.
    // Sans ces trois-là, « tolérant » finirait par vouloir dire « n'importe quoi passe »,
    // et le mot « illisible » ne voudrait plus rien dire du tout.
    test("un document qui n'est pas un objet", () {
      expect(ContenuDInvite.depuisJson('["Camille"]'), isNull);
      expect(ContenuDInvite.depuisJson('"Camille"'), isNull);
      expect(ContenuDInvite.depuisJson('42'), isNull);
    });

    test('du JSON malformé', () {
      expect(ContenuDInvite.depuisJson('{"name":'), isNull);
      expect(ContenuDInvite.depuisJson('pas du json'), isNull);
    });

    test('des octets vides', () {
      // Ce que rendrait un déchiffrement aboutissant sur du rien.
      expect(ContenuDInvite.depuisJson(''), isNull);
    });
  });
}
