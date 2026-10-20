// Editing a series from the app must not erase what the app does not show.

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/agenda.dart';
import 'package:ghostcal/services/api.dart';
import 'package:ghostcal/services/auth.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test(
    'deleting one occurrence keeps the series and adds the exception',
    () async {
      Map<String, dynamic>? corps;
      String? route;
      final api = ClientAPI(
        base: Uri.parse('https://cal.example.com'),
        client: MockClient((r) async {
          route = '${r.method} ${r.url.path}';
          corps = jsonDecode(r.body) as Map<String, dynamic>;
          return http.Response('', 204);
        }),
      )..poserLesJetons(const Jetons(acces: 'a', rafraichissement: 'r'));
      final agenda = Agenda(api: api, auth: Auth(api));
      final serie = DetailDEvenement(
        id: 'e1',
        calendrier: 'c1',
        debut: DateTime.utc(2026, 10, 5, 9),
        fin: DateTime.utc(2026, 10, 5, 10),
        fuseau: 'Europe/Zurich',
        journeeEntiere: false,
        scelle: 'sealed-blob',
        rrule: 'FREQ=WEEKLY',
        exdates: const ['2026-10-12T09:00:00.000Z'],
        rappelMinutes: 60,
      );

      await agenda.supprimerUneOccurrence(serie, DateTime.utc(2026, 10, 19, 9));

      expect(route, 'PUT /v1/me/calendar/events/e1');
      expect(corps!['rrule'], 'FREQ=WEEKLY');
      expect(corps!['reminder_minutes'], 60);
      expect(corps!['content'], 'sealed-blob');
      expect(corps!['exdates'], [
        '2026-10-12T09:00:00.000Z',
        '2026-10-19T09:00:00.000Z',
      ]);
      expect(serie.repete, isTrue);
    },
  );
}
