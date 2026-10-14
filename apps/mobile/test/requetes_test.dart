// What the app actually sends for the actions added to match the web.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/api.dart';
import 'package:ghostcal/services/auth.dart';
import 'package:ghostcal/services/erreurs.dart';
import 'package:ghostcal/services/reunions.dart';
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
}
