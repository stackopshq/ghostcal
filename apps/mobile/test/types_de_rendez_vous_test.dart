// Les règles des types de rendez-vous.
//
// La plus importante ne se voit pas à l'écran : la mise à jour est un `PUT` qui attend
// l'objet **complet**. N'envoyer que le champ modifié remettrait les autres à leur valeur
// par défaut — un utilisateur qui coupe un créneau depuis son téléphone perdrait ses
// tampons, son préavis et ses questions sans qu'aucune erreur ne le signale.

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/api.dart';
import 'package:ghostcal/services/types_de_rendez_vous.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Map<String, dynamic> brut({
  String id = 'id-1',
  String titre = 'Entretien',
  bool actif = true,
}) =>
    {
      'id': id,
      'organization_slug': 'stackops',
      'slug': 'entretien',
      'title': titre,
      'description': 'un entretien',
      'duration_min': 30,
      'slot_interval_min': 15,
      'buffer_before_min': 5,
      'buffer_after_min': 10,
      'min_notice_min': 120,
      'date_window_days': 60,
      'max_per_day': 4,
      'location_type': 'video',
      'active': actif,
      'questions': [
        {'id': 'q1', 'label': 'Sujet', 'type': 'text', 'required': true, 'options': []}
      ],
      'kind': 'one_on_one',
      'host_ids': ['h1'],
      'capacity': 1,
      'redirect_url': null,
    };

void main() {
  _temoinDuCorpsComplet();

  group("L'ordre", () {
    test('les actifs en premier, puis par titre', () {
      final ordre = TypesDeRendezVous.ordonner([
        TypeDeRendezVous.depuisJson(brut(id: 'b', titre: 'Beta', actif: false)),
        TypeDeRendezVous.depuisJson(brut(id: 'z', titre: 'Zulu')),
        TypeDeRendezVous.depuisJson(brut(id: 'a', titre: 'Alpha')),
      ]).map((t) => t.id).toList();
      expect(ordre, ['a', 'z', 'b']);
    });

    test("le tri par titre ignore la casse", () {
      // Sinon « entretien » se rangerait après « Zoom », et la liste paraîtrait
      // désordonnée sans raison visible.
      final ordre = TypesDeRendezVous.ordonner([
        TypeDeRendezVous.depuisJson(brut(id: 'z', titre: 'Zoom')),
        TypeDeRendezVous.depuisJson(brut(id: 'e', titre: 'entretien')),
      ]).map((t) => t.id).toList();
      expect(ordre, ['e', 'z']);
    });
  });

  group('Le lien public', () {
    test("se construit sur le serveur saisi, pas sur une constante", () {
      // Chaque client a son instance. Un lien vers le mauvais domaine ne mènerait nulle
      // part, et c'est le destinataire qui le découvrirait.
      final lien = TypesDeRendezVous.lienPublic(
        TypeDeRendezVous.depuisJson(brut()),
        serveur: 'https://ghostcal.stackops.ch',
      );
      expect(lien.toString(), 'https://ghostcal.stackops.ch/stackops/entretien');
    });

    test("une adresse inexploitable ne produit pas de lien bancal", () {
      for (final serveur in ['', 'pas une adresse', '/relatif']) {
        expect(
          TypesDeRendezVous.lienPublic(TypeDeRendezVous.depuisJson(brut()),
              serveur: serveur),
          isNull,
          reason: '« $serveur »',
        );
      }
    });
  });
}

// ─── Ce que la requête emporte réellement ───

/// Ce témoin est le plus important du fichier, et le seul qui regarde la requête émise
/// plutôt que le résultat d'un calcul.
///
/// La route est un `PUT` : elle **remplace**. Un client qui n'enverrait que `active`
/// remettrait tampons, préavis, fenêtre et questions à leur valeur par défaut, sans qu'aucune
/// erreur ne le signale. L'utilisateur ne s'en apercevrait qu'à la prochaine réservation.
void _temoinDuCorpsComplet() {
  group('La bascule renvoie tout', () {
    late Map<String, dynamic> corpsEnvoye;
    late String methode;
    late String chemin;

    ClientAPI clientQuiCapture() => ClientAPI(
          base: Uri.parse('https://ghostcal.example.com'),
          client: MockClient((requete) async {
            methode = requete.method;
            chemin = requete.url.path;
            corpsEnvoye = jsonDecode(requete.body) as Map<String, dynamic>;
            return http.Response('', 204);
          }),
        );

    test('la requête est un PUT sur le bon chemin', () async {
      await TypesDeRendezVous(api: clientQuiCapture())
          .basculer(TypeDeRendezVous.depuisJson(brut()), actif: false);
      expect(methode, 'PUT');
      expect(chemin, '/v1/me/event-types/id-1');
    });

    test('tous les réglages repartent, pas seulement celui qui change', () async {
      await TypesDeRendezVous(api: clientQuiCapture())
          .basculer(TypeDeRendezVous.depuisJson(brut()), actif: false);
      for (final champ in [
        'title',
        'duration_min',
        'slot_interval_min',
        'buffer_before_min',
        'buffer_after_min',
        'min_notice_min',
        'date_window_days',
        'max_per_day',
        'location_type',
        'questions',
        'kind',
        'host_ids',
        'capacity',
      ]) {
        expect(corpsEnvoye.containsKey(champ), isTrue, reason: 'champ absent : $champ');
      }
      expect(corpsEnvoye['buffer_after_min'], 10);
      expect((corpsEnvoye['questions'] as List).length, 1);
      expect(corpsEnvoye['active'], isFalse);
    });

    test('un champ que ce client ignore repart quand même', () async {
      // Un client plus ancien que le serveur écraserait sinon les réglages ajoutés
      // depuis. C'est pour cela que le corps repart du JSON reçu, plutôt que d'être
      // reconstruit champ par champ.
      final avecInconnu = brut()..['reglage_ajoute_plus_tard'] = 'valeur';
      await TypesDeRendezVous(api: clientQuiCapture())
          .basculer(TypeDeRendezVous.depuisJson(avecInconnu), actif: false);
      expect(corpsEnvoye['reglage_ajoute_plus_tard'], 'valeur');
    });

    test('les champs en lecture seule ne repartent pas', () async {
      // Le serveur les rend mais les refuse en écriture : les renvoyer ferait échouer la
      // requête sur une validation, pour des valeurs qu'on ne modifie pas.
      await TypesDeRendezVous(api: clientQuiCapture())
          .basculer(TypeDeRendezVous.depuisJson(brut()), actif: false);
      for (final lecture in ['id', 'organization_slug', 'slug', 'description']) {
        expect(corpsEnvoye.containsKey(lecture), isFalse, reason: lecture);
      }
    });
  });
}
