// What the app actually sends for the actions added to match the web.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/api.dart';
import 'package:ghostcal/services/auth.dart';
import 'package:ghostcal/services/erreurs.dart';
import 'package:ghostcal/services/reglages.dart';
import 'package:ghostcal/services/reunions.dart';
import 'package:ghostcal/services/types_de_rendez_vous.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('sending the video link posts it to the meeting', () async {
    late http.Request recue;
    final api = ClientAPI(
      base: Uri.parse('https://cal.example.com'),
      client: MockClient((r) async {
        recue = r;
        return http.Response('{}', 200);
      }),
    );
    await Reunions(api: api, auth: Auth(api)).envoyerLeLien('b1', 'https://zoom.us/j/1');
    expect(recue.method, 'POST');
    expect(recue.url.path, '/v1/me/meetings/b1/meeting-link');
    expect(jsonDecode(recue.body), {'url': 'https://zoom.us/j/1'});
  });

  test('a refused connection becomes an ErreurReseau, not a raw exception', () async {
    final api = ClientAPI(
      base: Uri.parse('https://cal.example.com'),
      client: MockClient((_) async => throw const SocketException('Connection refused')),
    );
    await expectLater(
      api.obtenir<List<dynamic>>('v1/me/tasks'),
      throwsA(isA<ErreurReseau>()
          .having((e) => e.genre, 'genre', GenreDErreurReseau.injoignable)),
    );
  });

  group('event types', () {
    late List<http.Request> recues;
    late TypesDeRendezVous service;
    setUp(() {
      recues = [];
      service = TypesDeRendezVous(
        api: ClientAPI(
          base: Uri.parse('https://cal.example.com'),
          client: MockClient((r) async {
            recues.add(r);
            return http.Response('{"id":"t1"}', 200);
          }),
        ),
      );
    });

    test('creating sends the web defaults under the fields given', () async {
      await service.creer({'title': 'Intro', 'duration_min': 45});
      final corps = jsonDecode(recues.single.body) as Map<String, dynamic>;
      expect(corps['title'], 'Intro');
      expect(corps['duration_min'], 45);
      expect(corps['kind'], 'solo');
      expect(corps['date_window_days'], 60);
    });

    test('saving sends everything back except read-only fields', () async {
      await service.enregistrer('t1', {
        'id': 't1',
        'organization_id': 'o',
        'organization_slug': 'clara',
        'slug': 'intro-1',
        'title': 'Intro',
        'questions': [
          {'label': 'Topic', 'type': 'text', 'required': true, 'options': <String>[]},
        ],
      });
      final r = recues.single;
      expect(r.method, 'PUT');
      expect(r.url.path, '/v1/me/event-types/t1');
      final corps = jsonDecode(r.body) as Map<String, dynamic>;
      expect(corps.keys, isNot(contains('slug')));
      expect(corps.keys, isNot(contains('id')));
      expect(corps['questions'], hasLength(1), reason: 'web-only settings must survive');
    });
  });

  test('creating a poll sends UTC slot starts and returns the public link', () async {
    late http.Request recue;
    final api = ClientAPI(
      base: Uri.parse('https://cal.example.com'),
      client: MockClient((r) async {
        recue = r;
        return http.Response(
            jsonEncode({'id': 'p1', 'slug': 'atelier-abc', 'title': 'Atelier',
              'duration_min': 60, 'status': 'open', 'options': [], 'voters': []}),
            201);
      }),
    );
    final cree = await Reglages(api: api).creerUnSondage(
      titre: 'Atelier',
      duree: 60,
      lieu: 'zoom',
      creneaux: [DateTime.utc(2026, 10, 20, 8), DateTime.utc(2026, 10, 21, 8)],
    );
    final corps = jsonDecode(recue.body) as Map<String, dynamic>;
    expect(corps['option_starts'], ['2026-10-20T08:00:00.000Z', '2026-10-21T08:00:00.000Z']);
    expect(Reglages.lienDuSondage(cree, Uri.parse('https://cal.example.com')).toString(),
        'https://cal.example.com/poll/atelier-abc');
  });
}

