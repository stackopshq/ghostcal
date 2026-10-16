// Booking reminders: which ones get scheduled, and the token race with the background
// refresh.

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/l10n/generated/app_localisations.dart';
import 'package:ghostcal/services/api.dart';
import 'package:ghostcal/services/rappels.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flutter/foundation.dart'
    show TargetPlatform, debugDefaultTargetPlatformOverride;
import 'package:flutter/widgets.dart' show Locale;

void main() {
  final maintenant = DateTime.utc(2026, 10, 15, 9);
  const dix = Duration(minutes: 10);

  Map<String, dynamic> ligne(
    String source,
    DateTime debut, {
    bool journee = false,
  }) => {
    'source': source,
    'start': debut.toIso8601String(),
    'end': debut.add(const Duration(minutes: 30)).toIso8601String(),
    'all_day': journee,
    'title': 'Camille Martin',
  };

  group('rappelsAPrevoir', () {
    test('keeps timed bookings only, ten minutes before', () {
      final prevus = rappelsAPrevoir(
        [
          ligne('booking', DateTime.utc(2026, 10, 15, 14)),
          ligne('event', DateTime.utc(2026, 10, 15, 15)),
          ligne('external', DateTime.utc(2026, 10, 15, 16)),
          ligne('booking', DateTime.utc(2026, 10, 16), journee: true),
        ],
        maintenant: maintenant,
        avance: dix,
      );

      expect(prevus, hasLength(1));
      expect(prevus.single.quand, DateTime.utc(2026, 10, 15, 13, 50));
      expect(prevus.single.debut, DateTime.utc(2026, 10, 15, 14));
    });

    test(
      'drops a reminder whose time has passed, even if the booking has not',
      () {
        final prevus = rappelsAPrevoir(
          [
            ligne('booking', maintenant.add(const Duration(minutes: 5))),
            ligne('booking', maintenant.add(const Duration(minutes: 11))),
          ],
          maintenant: maintenant,
          avance: dix,
        );

        expect(prevus.map((p) => p.debut), [
          maintenant.add(const Duration(minutes: 11)),
        ]);
      },
    );

    test('same start, same id: a refresh does not ring twice', () {
      final debut = DateTime.utc(2026, 10, 15, 14);
      final premiers = rappelsAPrevoir(
        [ligne('booking', debut)],
        maintenant: maintenant,
        avance: dix,
      );
      final seconds = rappelsAPrevoir(
        [ligne('booking', debut), ligne('booking', debut)],
        maintenant: maintenant,
        avance: dix,
      );

      expect(seconds, hasLength(1));
      expect(seconds.single.id, premiers.single.id);
    });

    test('sorted, and capped', () {
      final lignes = [
        for (var h = 40; h > 0; h--)
          ligne('booking', maintenant.add(Duration(hours: h))),
      ];
      final prevus = rappelsAPrevoir(
        lignes,
        maintenant: maintenant,
        avance: dix,
        maximum: 3,
      );

      expect(prevus.map((p) => p.debut), [
        maintenant.add(const Duration(hours: 1)),
        maintenant.add(const Duration(hours: 2)),
        maintenant.add(const Duration(hours: 3)),
      ]);
    });
  });

  test('the notification text names no one, in both languages', () {
    for (final code in ['fr', 'en']) {
      final l = lookupL(Locale(code));
      final textes = [l.rappelTitre, l.rappelCorps(10)];
      for (final texte in textes) {
        expect(texte, isNot(contains('Camille')));
      }
      expect(l.rappelCorps(10), contains('10'));
    }
  });

  group('refresh token used up elsewhere', () {
    ClientAPI client(List<String> refresh, {required Jetons? relus}) =>
        ClientAPI(
            base: Uri.parse('https://cal.example.com'),
            client: MockClient((r) async {
              if (r.url.path == '/v1/auth/refresh') {
                refresh.add(jsonDecode(r.body)['refresh_token'] as String);
                // r1 was already rotated by the other side.
                return http.Response('{"detail":"invalid"}', 401);
              }
              return r.headers['authorization'] == 'Bearer a2'
                  ? http.Response('[]', 200)
                  : http.Response('', 401);
            }),
          )
          ..poserLesJetons(const Jetons(acces: 'a1', rafraichissement: 'r1'))
          ..relireLesJetons = () async => relus;

    test('carries on with the tokens the other side saved', () async {
      final refresh = <String>[];
      final api = client(
        refresh,
        relus: const Jetons(acces: 'a2', rafraichissement: 'r2'),
      );

      expect(
        await api.obtenir<List<dynamic>>('v1/me/calendar/agenda'),
        isEmpty,
      );
      expect(refresh, ['r1']);
      expect(api.jetons?.rafraichissement, 'r2');
    });

    test('still ends the session when nothing newer was saved', () async {
      final api = client(
        [],
        relus: const Jetons(acces: 'a1', rafraichissement: 'r1'),
      );

      await expectLater(
        api.obtenir<List<dynamic>>('v1/me/calendar/agenda'),
        throwsA(isA<ErreurAPI>().having((e) => e.statut, 'statut', 401)),
      );
      expect(api.jetons, isNull);
    });
  });

  group('où les rappels sont offerts', () {
    tearDown(() => debugDefaultTargetPlatformOverride = null);

    test('les deux téléphones, et rien d\'autre', () {
      for (final plateforme in [TargetPlatform.android, TargetPlatform.iOS]) {
        debugDefaultTargetPlatformOverride = plateforme;
        expect(Rappels.disponible, isTrue, reason: '$plateforme doit les offrir');
      }
      // Le bureau n'a ni l'écran ni le besoin, et `Workmanager` n'y existe pas.
      for (final plateforme in [TargetPlatform.macOS, TargetPlatform.linux]) {
        debugDefaultTargetPlatformOverride = plateforme;
        expect(Rappels.disponible, isFalse, reason: '$plateforme ne doit pas les offrir');
      }
    });
  });

  // Un garde-fou plutôt qu'une mesure : iOS garde **64** notifications locales en
  // attente par application et laisse tomber les suivantes, sans rien dire. Comme iOS
  // planifie toute la fenêtre d'un coup au lieu de la rafraîchir, ce plafond est la
  // vraie borne. Quiconque relèvera `maximum` croisera ce témoin avant l'utilisateur
  // dont le huitième rendez-vous de la semaine n'a pas sonné.
  test('le plafond reste sous celui d\'iOS', () {
    expect(Rappels.maximum, lessThanOrEqualTo(64));
  });
}
