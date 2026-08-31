// Les vecteurs de contrat, portés depuis les tests Swift **valeur par valeur**.
//
// Ce fichier est l'accord entre les clients de la suite : les noms de champs des blobs
// scellés, la convention des jours, l'adresse qu'on accepte. Un vecteur qui changerait en
// traduisant serait un défaut, pas une adaptation — c'est la consigne qu'on s'est donnée
// avant de commencer le portage, et elle vaut plus que le reste de ce fichier.
//
// Ces tests ne touchent pas au natif : ils tournent en quelques secondes, sans appareil.
// La frontière avec Rust est éprouvée à part, dans `integration_test/coeur_test.dart`, qui
// exige une machine réelle — les deux ne se remplacent pas.

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/modeles/adresse.dart';
import 'package:ghostcal/modeles/contenus.dart';

void main() {
  group("L'adresse du serveur", () {
    test('un hôte nu devient du https', () {
      expect(
        AdresseDeServeur.normaliser('ghostcal.stackops.ch').toString(),
        'https://ghostcal.stackops.ch',
      );
    });

    test('la boucle locale reste en clair', () {
      // Un serveur de développement tourne en clair. L'exiger en https obligerait à taper
      // le schéma précisément là où on développe.
      for (final adresse in ['localhost:5173', '127.0.0.1:8080', 'localhost']) {
        expect(AdresseDeServeur.normaliser(adresse)?.scheme, 'http', reason: adresse);
      }
    });

    test('un hôte distant ne devient jamais du clair', () {
      // Les jetons de session y passeraient en lisible.
      expect(AdresseDeServeur.normaliser('192.168.1.50:8080')?.scheme, 'https');
      expect(AdresseDeServeur.normaliser('ghostcal.example.com')?.scheme, 'https');
    });

    test('un schéma explicite est conservé', () {
      expect(AdresseDeServeur.normaliser('http://ghostcal.example.com')?.scheme, 'http');
    });

    test("ce qui n'est pas une adresse est refusé", () {
      for (final saisie in ['', '   ', 'ftp://ghostcal.example.com', 'https://']) {
        expect(AdresseDeServeur.normaliser(saisie), isNull, reason: '« $saisie »');
      }
    });
  });

  group('Les contenus scellés gardent les noms de champs du web', () {
    // Ce sont ces noms qui font contrat. Les traduire en français aurait été la façon la
    // plus élégante de rendre les événements illisibles chez les deux autres clients.

    test('un événement', () {
      const contenu = ContenuDEvenement(
        title: 'Dentiste',
        description: 'contrôle annuel',
        location: 'Genève',
      );
      final json = jsonDecode(jsonEncode(contenu.versJson())) as Map<String, dynamic>;
      expect(json.keys.toSet(), {'title', 'description', 'location'});
    });

    test('une tâche', () {
      const contenu = ContenuDeTache(title: 'Passeport', notes: 'avant juin');
      final json = jsonDecode(jsonEncode(contenu.versJson())) as Map<String, dynamic>;
      expect(json.keys.toSet(), {'title', 'notes'});
    });

    test('un invité', () {
      const contenu = ContenuDInvite(
        name: 'Clara',
        answers: {'Sujet': 'Devis'},
        notes: 'rappeler le budget',
      );
      final json = jsonDecode(jsonEncode(contenu.versJson())) as Map<String, dynamic>;
      expect(json.keys.toSet(), {'name', 'answers', 'notes'});
    });
  });

  group("Ce qu'on ne sait pas lire", () {
    // La règle qui traverse toute l'application : un contenu illisible se dit, il ne fait
    // pas disparaître la ligne. Une ligne absente se lit comme « libre », ce qui est faux
    // et coûte un rendez-vous double.

    test('un contenu incomplet est refusé sans jeter', () {
      expect(ContenuDEvenement.depuisJson('{"title":"Dentiste"}'), isNull);
      expect(ContenuDeTache.depuisJson('{"title":"Passeport"}'), isNull);
    });

    test("ce qui n'est pas du JSON est refusé sans jeter", () {
      expect(ContenuDEvenement.depuisJson('pas du json'), isNull);
      expect(ContenuDeTache.depuisJson(''), isNull);
      expect(ContenuDInvite.depuisJson('[]'), isNull);
    });

    test('un contenu complet se relit', () {
      final contenu = ContenuDEvenement.depuisJson(
        '{"title":"Dentiste","description":"","location":"Genève"}',
      );
      expect(contenu?.title, 'Dentiste');
      expect(contenu?.location, 'Genève');
    });
  });

  group("Les réponses d'un invité", () {
    test('se trient par question', () {
      // Un dictionnaire n'a pas d'ordre : les afficher tels quels les ferait changer de
      // place à chaque lecture, et donnerait l'impression que le contenu bouge tout seul.
      final contenu = ContenuDInvite.depuisJson(
        '{"name":"Clara","answers":{"Zèbre":"z","Alpha":"a","Miel":"m"},"notes":""}',
      );
      expect(
        contenu?.reponsesTriees.map((e) => e.key).toList(),
        ['Alpha', 'Miel', 'Zèbre'],
      );
    });
  });
}
