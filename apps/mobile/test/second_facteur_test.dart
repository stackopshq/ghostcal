// Le second facteur : le serveur le réclamait, le client ne le connaissait pas.
//
// POURQUOI CE FICHIER EXISTE
// --------------------------
// Le TOTP est arrivé sur `main` pendant que la branche mobile avançait de son
// côté. `/v1/auth/login` répond désormais 401 en portant `mfa_required` et
// `mfa_type`, et `git grep -i mfa` sur `apps/mobile/lib` rendait **zéro
// occurrence**. Sur un compte à second facteur, l'application montrait donc un
// message d'échec sur un mot de passe pourtant bon, sans aucune issue.
//
// Deux choses manquaient, et il fallait les deux :
//
//   1. `_messageDErreur` savait lire un `detail` CHAÎNE et un `detail` LISTE —
//      pas un `detail` OBJET, qui est justement la forme du refus MFA. On
//      tombait jusqu'au message générique « Le serveur a répondu 401 », encore
//      moins parlant que « identifiants invalides » ;
//   2. rien n'envoyait `totp_code`, et rien n'ouvrait de champ pour le saisir.
//
// CE QUE CES TESTS SURVEILLENT
// -----------------------------
// La forme exacte du contrat, telle que `auth_routes.py` l'écrit — `detail`
// imbriqué compris, parce que FastAPI enveloppe ce qu'on lui donne. Un test qui
// affirmerait une forme plate passerait ici et échouerait en production.

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/api.dart';
import 'package:ghostcal/services/auth.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// La réponse du serveur quand il réclame un second facteur.
///
/// `detail` est un OBJET à l'intérieur de `detail` : FastAPI enveloppe le
/// dictionnaire passé à `HTTPException`. C'est cette imbrication que le client
/// ne savait pas lire.
http.Response refus(
  int statut,
  String phrase, {
  String? bloqueJusqua,
}) =>
    http.Response(
      jsonEncode({
        'detail': {
          'detail': phrase,
          'mfa_required': true,
          'mfa_type': 'totp',
          'locked_until': ?bloqueJusqua,
        }
      }),
      statut,
      headers: const {'content-type': 'application/json'},
    );

void main() {
  group("L'exigence de second facteur", () {
    test('un 401 « code requis » devient SecondFacteurRequis, pas une erreur', () async {
      final auth = Auth(ClientAPI(
        base: Uri.parse('https://ghostcal.example.com'),
        client: MockClient((_) async => refus(401, 'two-factor code required')),
      ));

      await expectLater(
        auth.seConnecter(email: 'clara@example.com', motDePasse: 'phrase'),
        throwsA(isA<SecondFacteurRequis>()
            .having((e) => e.genre, 'genre', 'totp')
            .having((e) => e.codeRefuse, 'codeRefuse', isFalse)
            .having((e) => e.estBloque, 'estBloque', isFalse)),
      );
    });

    // Un code manquant et un code faux demandent la même chose mais ne se
    // disent pas pareil : « entrez votre code » après en avoir tapé un est
    // déroutant.
    test('un code refusé se distingue d’un code absent', () async {
      final auth = Auth(ClientAPI(
        base: Uri.parse('https://ghostcal.example.com'),
        client: MockClient((_) async => refus(401, 'invalid two-factor code')),
      ));

      await expectLater(
        auth.seConnecter(
            email: 'clara@example.com', motDePasse: 'phrase', codeTotp: '000000'),
        throwsA(isA<SecondFacteurRequis>().having((e) => e.codeRefuse, 'codeRefuse', isTrue)),
      );
    });

    // Le serveur rend 429 et dit jusqu'à quand. Sans lire cette heure, on
    // réessaie en boucle une saisie qui ne peut pas aboutir avant l'échéance.
    test('le blocage porte son échéance', () async {
      final auth = Auth(ClientAPI(
        base: Uri.parse('https://ghostcal.example.com'),
        client: MockClient((_) async => refus(429, 'too many two-factor attempts',
            bloqueJusqua: '2026-09-26T18:30:00+00:00')),
      ));

      await expectLater(
        auth.seConnecter(email: 'clara@example.com', motDePasse: 'phrase'),
        throwsA(isA<SecondFacteurRequis>()
            .having((e) => e.estBloque, 'estBloque', isTrue)
            .having((e) => e.bloqueJusqua?.toUtc().hour, 'heure', 18)),
      );
    });

    // LE test du champ. Sans lui, on pouvait « gérer » le second facteur tout
    // en n'envoyant jamais de code, et la demande reviendrait indéfiniment.
    test('le code part sous le nom que le serveur attend', () async {
      Map<String, dynamic>? envoye;
      final auth = Auth(ClientAPI(
        base: Uri.parse('https://ghostcal.example.com'),
        client: MockClient((requete) async {
          // Seulement la connexion : `deverrouiller` enchaîne d'autres appels,
          // au corps vide, et décoder le leur ferait échouer le bouchon sur un
          // détail qui n'a rien à voir avec ce qu'on éprouve.
          if (requete.url.path.endsWith('/auth/login')) {
            envoye = jsonDecode(requete.body) as Map<String, dynamic>;
            return http.Response(
              jsonEncode({'access_token': 'a', 'refresh_token': 'r'}),
              200,
              headers: const {'content-type': 'application/json'},
            );
          }
          // Une LISTE vide : c'est ce que `deverrouiller` va chercher ensuite
          // (les générations de clés d'organisation). Un objet lui ferait lever
          // une erreur de type, qui n'est pas ce qu'on éprouve ici.
          return http.Response('[]', 200,
              headers: const {'content-type': 'application/json'});
        }),
      ));

      // Le déverrouillage du coffre échouera — il n'y a pas de cœur Rust ici —
      // et c'est sans importance : `seConnecter` rend la raison au lieu de
      // jeter, et c'est la REQUÊTE qu'on regarde.
      await auth.seConnecter(
          email: 'clara@example.com', motDePasse: 'phrase', codeTotp: '123456');

      expect(envoye?['totp_code'], '123456');
      expect(envoye?['password'], 'phrase');
    });

    // Un champ vide n'est pas « pas de code » : le serveur borne la longueur du
    // champ, et lui envoyer une chaîne vide n'est pas la même chose que de
    // l'omettre.
    test('sans code, la clé est absente et non vide', () async {
      Map<String, dynamic>? envoye;
      final auth = Auth(ClientAPI(
        base: Uri.parse('https://ghostcal.example.com'),
        client: MockClient((requete) async {
          // Seulement la connexion : `deverrouiller` enchaîne d'autres appels,
          // au corps vide, et décoder le leur ferait échouer le bouchon sur un
          // détail qui n'a rien à voir avec ce qu'on éprouve.
          if (requete.url.path.endsWith('/auth/login')) {
            envoye = jsonDecode(requete.body) as Map<String, dynamic>;
            return http.Response(
              jsonEncode({'access_token': 'a', 'refresh_token': 'r'}),
              200,
              headers: const {'content-type': 'application/json'},
            );
          }
          // Une LISTE vide : c'est ce que `deverrouiller` va chercher ensuite
          // (les générations de clés d'organisation). Un objet lui ferait lever
          // une erreur de type, qui n'est pas ce qu'on éprouve ici.
          return http.Response('[]', 200,
              headers: const {'content-type': 'application/json'});
        }),
      ));

      await auth.seConnecter(email: 'clara@example.com', motDePasse: 'phrase');
      expect(envoye!.containsKey('totp_code'), isFalse);

      await auth.seConnecter(
          email: 'clara@example.com', motDePasse: 'phrase', codeTotp: '');
      expect(envoye!.containsKey('totp_code'), isFalse);
    });

    // Un 401 ORDINAIRE — mot de passe faux — doit rester une erreur. Le
    // confondre avec une demande de code ouvrirait un champ que personne ne
    // peut remplir.
    test('un mot de passe faux reste une erreur, pas une demande de code', () async {
      final auth = Auth(ClientAPI(
        base: Uri.parse('https://ghostcal.example.com'),
        client: MockClient((_) async => http.Response(
              jsonEncode({'detail': 'invalid email or password'}),
              401,
              headers: const {'content-type': 'application/json'},
            )),
      ));

      await expectLater(
        auth.seConnecter(email: 'clara@example.com', motDePasse: 'faux'),
        throwsA(isA<ErreurAPI>().having((e) => e.message, 'message', contains('invalid email'))),
      );
    });
  });

  group("Le message d'erreur", () {
    // C'est la moitié qui manquait côté transport : sans elle, l'utilisateur
    // voyait « Le serveur a répondu 401 » même quand le serveur avait écrit
    // une phrase parfaitement claire.
    test('un detail OBJET rend sa phrase, pas le message générique', () async {
      final api = ClientAPI(
        base: Uri.parse('https://ghostcal.example.com'),
        client: MockClient((_) async => refus(401, 'two-factor code required')),
      );

      try {
        await api.envoyer<Map<String, dynamic>>('POST', 'v1/auth/login', const {});
        fail('la requête aurait dû échouer');
      } on ErreurAPI catch (e) {
        expect(e.message, 'two-factor code required');
        expect(e.details?['mfa_required'], isTrue);
        expect(e.details?['mfa_type'], 'totp');
      }
    });
  });
}
