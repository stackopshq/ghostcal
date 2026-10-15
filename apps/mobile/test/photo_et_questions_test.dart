// Profile photo upload and event-type questions, added to match the web.

import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/ecrans/questions_du_type.dart';
import 'package:ghostcal/services/api.dart';
import 'package:ghostcal/services/reglages.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'harnais.dart';

void main() {
  test('the photo goes as multipart under "fichier", and again after a token refresh', () async {
    final recues = <http.Request>[];
    final api = ClientAPI(
      base: Uri.parse('https://cal.example.com'),
      client: MockClient((r) async {
        recues.add(r);
        if (r.url.path == '/v1/auth/refresh') {
          return http.Response(
            jsonEncode({'access_token': 'a2', 'refresh_token': 'r2'}),
            200,
          );
        }
        final premier =
            recues.where((x) => x.url.path == '/v1/me/profile/avatar').length ==
            1;
        return http.Response('', premier ? 401 : 204);
      }),
    )..poserLesJetons(const Jetons(acces: 'a1', rafraichissement: 'r1'));

    await Reglages(api: api)
        .televerserLaPhoto(Uint8List.fromList([1, 2, 3]), 'moi.jpg');

    final envois = recues
        .where((r) => r.url.path == '/v1/me/profile/avatar')
        .toList();
    expect(envois, hasLength(2));
    for (final envoi in envois) {
      expect(envoi.headers['content-type'], startsWith('multipart/form-data'));
      final corps = latin1.decode(envoi.bodyBytes);
      expect(corps, contains('name="fichier"; filename="moi.jpg"'));
    }
    expect(envois.last.headers['authorization'], 'Bearer a2');
  });

  test('the photo is read as bytes', () async {
    final api = ClientAPI(
      base: Uri.parse('https://cal.example.com'),
      client: MockClient((r) async {
        expect(r.url.path, '/v1/me/profile/avatar/u1');
        return http.Response.bytes(
          [9, 8, 7],
          200,
          headers: {'content-type': 'image/webp'},
        );
      }),
    );
    expect(await Reglages(api: api).photo('u1'), [9, 8, 7]);
  });

  testWidgets('adding a choice question yields the web shape', (tester) async {
    List<Map<String, dynamic>>? recues;
    await tester.pumpWidget(
      appDEpreuve(
        Scaffold(
          body: QuestionsDuType(
            questions: const [],
            changer: (q) => recues = q,
          ),
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('question.ajouter')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('question.libelle')),
      'Votre entreprise ?',
    );
    await tester.tap(find.byKey(const Key('question.type')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Liste de choix').last);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('question.options')),
      'PME\n\n Grand groupe \n',
    );
    await tester.pump();
    await tester.tap(find.byKey(const Key('question.valider')));
    await tester.pumpAndSettle();

    expect(recues, hasLength(1));
    final q = recues!.single;
    expect(q['id'], matches(RegExp(r'^q1_[a-z0-9]{5}$')));
    expect(q['label'], 'Votre entreprise ?');
    expect(q['type'], 'select');
    expect(q['required'], false);
    expect(q['options'], ['PME', 'Grand groupe']);
  });

  testWidgets('editing keeps the id answers are keyed by', (tester) async {
    List<Map<String, dynamic>>? recues;
    const existante = {
      'id': 'q1_abcde',
      'label': 'Téléphone',
      'type': 'phone',
      'required': true,
      'options': <String>[],
    };
    await tester.pumpWidget(
      appDEpreuve(
        Scaffold(
          body: QuestionsDuType(
            questions: [Map.of(existante)],
            changer: (q) => recues = q,
          ),
        ),
      ),
    );
    await tester.tap(find.byKey(const Key('question.0')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('question.libelle')), 'Mobile');
    await tester.pump();
    await tester.tap(find.byKey(const Key('question.valider')));
    await tester.pumpAndSettle();
    expect(recues!.single['id'], 'q1_abcde');
    expect(recues!.single['label'], 'Mobile');
    expect(recues!.single['required'], true);
  });
}
