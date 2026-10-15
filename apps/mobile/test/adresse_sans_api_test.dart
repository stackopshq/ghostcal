// Une adresse qui authentifie n'est pas pour autant la bonne.
//
// ─── Ce qui s'est passé ───
//
// Relevé sur `cal.ghostsuite.cloud` depuis l'iPhone : l'API y vit sous `/api`, et le
// proxy laisse passer `/v1/auth/*` sans préfixe. Mesuré à la main :
//
//   /v1/auth/login        → 405 (la route existe)
//   /v1/auth/zk-keys      → 401 (la route existe)
//   /v1/me/profile        → 404        /api/v1/me/profile        → 401
//   /v1/me/calendars      → 404        /api/v1/me/calendars      → 401
//   /v1/me/organizations  → 404        /api/v1/me/organizations  → 401
//
// La connexion réussissait, le coffre s'ouvrait — ce sont les deux seules routes
// `auth` — puis l'agenda affichait « Le serveur a répondu 404 ». Exact, et sans issue :
// rien ne disait que l'adresse était en cause, puisqu'elle venait d'authentifier.
//
// ─── Pourquoi la sonde est sur `v1/me/organizations` ───
//
// Parce qu'un 404 y est **impossible** autrement : tout compte authentifié appartient à
// au moins une organisation. Sonder une route dont la ressource peut manquer rendrait
// le témoin ambigu, et confondrait « mauvaise adresse » avec « rien à montrer ».

import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/erreurs.dart';
import 'package:ghostcal/services/session.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

http.Response json(Object corps, [int statut = 200]) => http.Response(
      jsonEncode(corps),
      statut,
      headers: const {'content-type': 'application/json'},
    );

/// Un serveur qui authentifie, et qui ne sert rien d'autre sous cette base.
MockClient leProxyQuiNeLaissePasserQueAuth({required bool sertLeReste}) =>
    MockClient((requete) async {
      final chemin = requete.url.path;
      if (chemin.endsWith('/v1/auth/login')) {
        return json({'access_token': 'a', 'refresh_token': 'r'});
      }
      // Le coffre : une liste vide de générations suffit. `deverrouiller` n'ouvre alors
      // aucune clé, ce que `seConnecter` rend comme un échec de coffre — pas comme une
      // panne, et surtout pas comme une erreur d'adresse. C'est exactement l'état dans
      // lequel la sonde doit quand même parler.
      if (chemin.endsWith('/v1/auth/zk-keys')) return json(const []);
      if (chemin.endsWith('/v1/me/organizations')) {
        return sertLeReste
            ? json([
                {'id': 'org-1', 'name': 'StackOps', 'slug': 'stackops'}
              ])
            : json({'detail': 'Not Found'}, 404);
      }
      return json({'detail': 'Not Found'}, 404);
    });

void main() {
  // Une adresse acceptée est **enregistrée** : la sonde franchie, `_adopter` écrit
  // dans le trousseau, qui passe par un canal de plateforme.
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  group("L'adresse du serveur", () {
    test('un 404 après une connexion réussie nomme l\'adresse, pas la ressource',
        () async {
      final session = Session(client: leProxyQuiNeLaissePasserQueAuth(sertLeReste: false))
        ..serveur = 'cal.ghostsuite.cloud'
        ..email = 'clara@example.com';

      await session.seConnecter(motDePasse: 'phrase');

      expect(
        session.erreur,
        isA<AdresseSansApi>(),
        reason: 'Sans cela, l\'écran dit « Le serveur a répondu 404 » sur l\'agenda, '
            'trois écrans plus loin, et rien ne ramène à l\'adresse.',
      );
      // Et la base fautive ne doit pas être adoptée : l'application resterait dehors
      // avec un client qui ne peut rien faire.
      expect(session.etat, isNot(Etat.ouvert));
    });

    test('une adresse qui sert tout passe la sonde', () async {
      final session = Session(client: leProxyQuiNeLaissePasserQueAuth(sertLeReste: true))
        ..serveur = 'cal.ghostsuite.cloud/api'
        ..email = 'clara@example.com';

      await session.seConnecter(motDePasse: 'phrase');

      expect(session.erreur, isNull);
      // Le coffre reste fermé — le faux serveur ne rend aucune génération de clés — et
      // c'est bien ce qu'il faut distinguer d'une adresse invalide.
      expect(session.etat, Etat.coffreFerme);
    });

    test('le chemin de la base est conservé dans les requêtes', () async {
      final chemins = <String>[];
      final session = Session(
        client: MockClient((requete) async {
          chemins.add(requete.url.path);
          if (requete.url.path.endsWith('/v1/auth/login')) {
            return json({'access_token': 'a', 'refresh_token': 'r'});
          }
          if (requete.url.path.endsWith('/v1/auth/zk-keys')) return json(const []);
          return json([
            {'id': 'org-1', 'name': 'StackOps', 'slug': 'stackops'}
          ]);
        }),
      )
        ..serveur = 'cal.ghostsuite.cloud/api'
        ..email = 'clara@example.com';

      await session.seConnecter(motDePasse: 'phrase');

      expect(
        chemins,
        everyElement(startsWith('/api/v1/')),
        reason: 'Le correctif donné à l\'utilisateur — ajouter « /api » — ne tient que '
            'si `ClientAPI` concatène bien le chemin de la base.',
      );
    });
  });
}
