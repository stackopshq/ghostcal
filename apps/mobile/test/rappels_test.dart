// Booking reminders: which ones get scheduled, the token race with the background
// refresh, and the one thing macOS needs that Android does not.

import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
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
  TestWidgetsFlutterBinding.ensureInitialized();
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

  /// ─── Ce que macOS demande en plus, et ce qu'il ne doit pas demander ───
  ///
  /// Android réveille une application fermée ; `NSBackgroundActivityScheduler` non. Le
  /// rafraîchissement n'a donc lieu sur un Mac que tant que l'application tourne, d'où
  /// l'inscription aux ouvertures de session. Elle n'existe que là : posée partout, elle
  /// ferait lever une `MissingPluginException` sur Android — au démarrage, dans `amorcer`,
  /// donc avant le premier écran.
  group('l\'ouverture de session', () {
    const canal = MethodChannel(Rappels.canalMacos);
    late List<MethodCall> appels;
    var inscrit = false;

    setUp(() {
      FlutterSecureStorage.setMockInitialValues({});
      appels = [];
      inscrit = false;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(canal, (appel) async {
            appels.add(appel);
            if (appel.method == 'lancerALOuvertureDeSession') {
              inscrit = (appel.arguments as Map)['valeur'] == true;
            }
            return inscrit;
          });
    });

    tearDown(() {
      debugDefaultTargetPlatformOverride = null;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(canal, null);
    });

    test(
      'sur macOS, l\'état est demandé au système et non relu d\'un réglage',
      () async {
        debugDefaultTargetPlatformOverride = TargetPlatform.macOS;
        final rappels = Rappels();
        await rappels.amorcer();
        expect(appels.single.method, 'lanceALOuvertureDeSession');
        expect(rappels.aLOuvertureDeSession, isFalse);

        expect(await rappels.lancerALOuvertureDeSession(true), isTrue);
        expect(rappels.aLOuvertureDeSession, isTrue);
      },
    );

    /// Le système peut refuser : l'utilisateur a pu interdire le lancement automatique
    /// depuis les Réglages Système. L'interrupteur doit alors retomber **et le dire**,
    /// pas afficher un réglage actif devant un système qui a dit non.
    test('un refus du système ne laisse pas l\'interrupteur allumé', () async {
      debugDefaultTargetPlatformOverride = TargetPlatform.macOS;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(canal, (_) async => false);
      final rappels = Rappels();
      expect(await rappels.lancerALOuvertureDeSession(true), isFalse);
      expect(rappels.aLOuvertureDeSession, isFalse);
    });

    test('sur Android, le canal n\'est jamais sollicité', () async {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      final rappels = Rappels();
      await rappels.amorcer();
      expect(await rappels.lancerALOuvertureDeSession(true), isFalse);
      expect(
        appels,
        isEmpty,
        reason: 'le canal n\'existe pas là-bas : amorcer lèverait au démarrage',
      );
    });

    test('reminders exist on Android, iOS and macOS, and nowhere else', () {
      for (final plateforme in [
        TargetPlatform.android,
        TargetPlatform.iOS,
        TargetPlatform.macOS,
      ]) {
        debugDefaultTargetPlatformOverride = plateforme;
        expect(Rappels.disponible, isTrue, reason: '$plateforme');
      }
      for (final plateforme in [TargetPlatform.iOS, TargetPlatform.linux]) {
        debugDefaultTargetPlatformOverride = plateforme;
        expect(Rappels.surMacos, isFalse, reason: '$plateforme');
      }
      debugDefaultTargetPlatformOverride = TargetPlatform.linux;
      expect(Rappels.disponible, isFalse);
    });
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

  // Un garde-fou plutôt qu'une mesure : iOS garde **64** notifications locales en
  // attente par application et laisse tomber les suivantes, sans rien dire. Comme iOS
  // planifie toute la fenêtre d'un coup au lieu de la rafraîchir, ce plafond est la
  // vraie borne. Quiconque relèvera `maximum` croisera ce témoin avant l'utilisateur
  // dont le huitième rendez-vous de la semaine n'a pas sonné.
  test('le plafond reste sous celui d\'iOS', () {
    expect(Rappels.maximum, lessThanOrEqualTo(64));
  });
}
