// La langue de l'interface dite au serveur.
//
// Le serveur ne produit qu'**un** texte visible par l'utilisateur : le nom du calendrier
// par défaut. Il le produit paresseusement, à la première lecture de `GET /v1/me/calendars`
// et non à l'inscription — si bien que la requête qui le crée part d'un client authentifié
// qui, lui, connaît sa langue. Il suffit qu'il le dise.
//
// Sans cet en-tête, un anglophone reçoit « Mon agenda » et le garde : jusqu'au 22 octobre
// aucune route ne renommait un calendrier, et la capture App Store anglaise l'affichait.

import 'package:flutter/widgets.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/api.dart';
import 'package:ghostcal/services/apparence.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  group("l'en-tête", () {
    late List<http.Request> recues;

    ClientAPI client() {
      recues = [];
      return ClientAPI(
        base: Uri.parse('https://cal.example.com'),
        client: MockClient((r) async {
          recues.add(r);
          return http.Response('[]', 200);
        }),
      );
    }

    test('part en accept-language, pas en en-tête maison', () async {
      // L'en-tête standard et non un `x-` à nous : un navigateur l'envoie déjà sans qu'on
      // le lui demande, donc le serveur n'a qu'une seule chose à lire pour ses deux
      // clients. Un en-tête maison obligerait le web à en ajouter un second.
      final api = client()..poserLaLangue('en');
      await api.obtenir<List<dynamic>>('v1/me/calendars');
      expect(recues.single.headers['accept-language'], 'en');
    });

    test("tant que personne ne l'a posée, rien n'est envoyé", () async {
      // Un en-tête vide ou absent laisse le serveur sur son comportement d'avant. Envoyer
      // `accept-language: ` vide lui ferait lire une langue qui n'existe pas.
      final api = client();
      await api.obtenir<List<dynamic>>('v1/me/calendars');
      expect(recues.single.headers.containsKey('accept-language'), isFalse);
    });

    test(
      'elle suit les changements, elle ne se fige pas à la connexion',
      () async {
        final api = client()..poserLaLangue('fr');
        await api.obtenir<List<dynamic>>('v1/me/calendars');
        api.poserLaLangue('en');
        await api.obtenir<List<dynamic>>('v1/me/calendars');
        expect(recues.map((r) => r.headers['accept-language']).toList(), [
          'fr',
          'en',
        ]);
      },
    );
  });

  group('la langue effective', () {
    test('un choix explicite vaut pour lui-même', () async {
      final apparence = Apparence();
      await apparence.choisirLaLangue(ChoixDeLangue.anglais);
      expect(apparence.codeDeLangue, 'en');
      await apparence.choisirLaLangue(ChoixDeLangue.francais);
      expect(apparence.codeDeLangue, 'fr');
    });

    test(
      "« celle de l'appareil » se résout, elle ne reste pas nulle",
      () async {
        // C'est le cas par défaut, et le seul qui compte vraiment : personne ne va dans les
        // réglages avant de voir son premier calendrier. Rendre `null` ici n'enverrait aucun
        // en-tête et laisserait précisément l'anglophone avec « Mon agenda ».
        final apparence = Apparence();
        await apparence.amorcer();
        expect(apparence.langue, ChoixDeLangue.appareil);
        expect(apparence.codeDeLangue, isIn(const ['fr', 'en']));
      },
    );

    test('une langue tierce retombe sur le français', () {
      // Le repli documenté de l'application. L'en-tête doit dire la même chose que
      // l'écran, sans quoi le serveur nommerait le calendrier dans une langue que
      // l'interface ne parle pas.
      expect(
        codeDeLangueDepuis(ChoixDeLangue.appareil, const Locale('de')),
        'fr',
      );
    });

    test("l'appareil décide quand rien n'a été choisi", () {
      expect(
        codeDeLangueDepuis(ChoixDeLangue.appareil, const Locale('en')),
        'en',
      );
      expect(
        codeDeLangueDepuis(ChoixDeLangue.appareil, const Locale('fr')),
        'fr',
      );
    });

    test("un choix explicite l'emporte sur l'appareil", () {
      // Quelqu'un qui met l'application en anglais sur un téléphone français doit avoir
      // « My calendar » : c'est l'écran qu'il regarde, pas le système.
      expect(
        codeDeLangueDepuis(ChoixDeLangue.anglais, const Locale('fr')),
        'en',
      );
      expect(
        codeDeLangueDepuis(ChoixDeLangue.francais, const Locale('en')),
        'fr',
      );
    });
  });
}
