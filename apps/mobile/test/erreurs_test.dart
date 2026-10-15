// What users read when something fails. Screens used to show `'$e'`, which put Dart and
// Java class names on screen ("ClientException with SocketException: Connection
// refused (OS Error…"), observed on a Redmi Note 9S when the server was unreachable.

import 'dart:async';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/l10n/generated/app_localisations.dart';
import 'package:ghostcal/services/api.dart';
import 'package:ghostcal/services/auth.dart';
import 'package:ghostcal/services/erreurs.dart';
import 'package:http/http.dart' as http;

final fr = lookupL(const Locale('fr'));
final en = lookupL(const Locale('en'));

void main() {
  group('transport failures are classified', () {
    test('refused connection', () {
      final e = ErreurReseau.depuis(
          http.ClientException('SocketException: Connection refused'));
      expect(e?.genre, GenreDErreurReseau.injoignable);
    });
    test('socket error', () {
      expect(ErreurReseau.depuis(const SocketException('x'))?.genre,
          GenreDErreurReseau.injoignable);
    });
    test('timeout', () {
      expect(ErreurReseau.depuis(TimeoutException('x'))?.genre, GenreDErreurReseau.delai);
    });
    test('TLS', () {
      expect(ErreurReseau.depuis(const HandshakeException('x'))?.genre,
          GenreDErreurReseau.certificat);
    });
    test('anything else is not a network error', () {
      expect(ErreurReseau.depuis(StateError('x')), isNull);
    });
  });

  group('lisible', () {
    test('never shows a class name', () {
      final texte = lisible(
          ErreurReseau.depuis(http.ClientException('SocketException'))!, fr);
      expect(texte, isNot(contains('Exception')));
      expect(texte, fr.erreurServeurInjoignable);
    });

    test('speaks the screen language', () {
      final e = ErreurReseau.depuis(TimeoutException('x'))!;
      expect(lisible(e, fr), fr.erreurServeurLent);
      expect(lisible(e, en), en.erreurServeurLent);
      expect(lisible(e, fr), isNot(lisible(e, en)));
    });

    test('a 401 means wrong credentials on the sign-in form only', () {
      final e = ErreurAPI(401, 'invalid credentials');
      expect(lisible(e, fr, connexion: true), fr.erreurIdentifiants);
      expect(lisible(e, fr), fr.erreurSessionExpiree);
    });

    test('server errors and throttling get our own sentence', () {
      expect(lisible(ErreurAPI(503, 'Service Unavailable'), fr), fr.erreurServeur);
      expect(lisible(ErreurAPI(429, 'Too Many Requests'), fr), fr.erreurTropDEssais);
    });

    test('a 4xx the server explained keeps its sentence', () {
      expect(lisible(ErreurAPI(409, 'slug already taken'), fr), 'slug already taken');
    });

    test('vault errors are translated, not shown in French everywhere', () {
      expect(lisible(ErreurDAuth.phraseIncorrecte, en), en.erreurPhraseIncorrecte);
      expect(lisible(ErreurDAuth.coffreFerme, en), en.coffreFermeChiffrementImpossible);
    });

    test('a bare status code is worded in the screen language', () {
      expect(lisible(ErreurAPI(418, ''), en), en.erreurStatut(418));
    });

    test('unknown failures fall back to a generic sentence', () {
      expect(lisible(StateError('boom'), en), en.erreurInattendue);
    });
  });
}
