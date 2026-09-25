// Les deux règles des réglages qui se cassent en silence.
//
// La convention des jours et le champ nul explicite : dans les deux cas, l'erreur produit
// un écran parfaitement cohérent, et faux.

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/api.dart';
import 'package:ghostcal/services/reglages.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flutter/widgets.dart';
import 'package:ghostcal/l10n/generated/app_localisations.dart';

// Les deux traductions, chargées directement : `roleLisible` prend un `L` et n'a besoin
// d'aucun arbre de widgets. Les instancier ici permet d'éprouver les deux langues dans le
// même test, plutôt que de croire l'une sur parole.
final fr = lookupL(const Locale('fr'));
final en = lookupL(const Locale('en'));

void main() {
  group('La convention des jours', () {
    // Le serveur compte 0 = lundi. `DateTime` de Dart compte 1 = lundi, et Java
    // 1 = dimanche. Confondre les trois décale tout l'horaire d'un jour : l'écran reste
    // cohérent, il affiche simplement un horaire qui n'est pas celui qui gouverne les
    // réservations. Personne ne le remarque avant qu'un invité réserve un dimanche.
    RegleDHoraire regle(int jour) =>
        RegleDHoraire.depuisJson({'weekday': jour, 'start': '09:00', 'end': '12:00'});

    test('zéro est lundi, six est dimanche', () {
      expect(regle(0).jour, 'lundi');
      expect(regle(6).jour, 'dimanche');
    });

    test('les sept jours sont couverts, dans le bon ordre', () {
      expect(
        [for (var j = 0; j < 7; j++) regle(j).jour],
        ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'],
      );
    });

    test('une valeur hors bornes se signale, elle ne se ramène pas', () {
      // Le modulo ramènerait n'importe quel entier dans les clous : un `weekday` de 42
      // s'afficherait « lundi », une valeur fausse présentée avec l'assurance d'une vraie.
      // Un point d'interrogation se remarque ; un mauvais jour, non.
      for (final aberrant in [-1, 7, 42]) {
        expect(regle(aberrant).jour, '?', reason: '$aberrant');
      }
    });

    test('un champ absent ne passe pas pour lundi', () {
      expect(RegleDHoraire.depuisJson({'start': '09:00', 'end': '12:00'}).jour, '?');
    });
  });

  group('Le profil', () {
    late Map<String, dynamic> corpsEnvoye;

    ClientAPI clientQuiCapture() => ClientAPI(
          base: Uri.parse('https://ghostcal.example.com'),
          client: MockClient((requete) async {
            corpsEnvoye = jsonDecode(requete.body) as Map<String, dynamic>;
            return http.Response(
              jsonEncode({
                'id': 'u1',
                'email': 'clara@example.com',
                'name': 'Clara',
                'timezone': 'Europe/Zurich',
                'email_verified': true,
                'avatar_url': null,
              }),
              200,
              headers: {'content-type': 'application/json'},
            );
          }),
        );

    test('une photo retirée part comme un nul explicite', () async {
      // La route est un `PUT` : elle remplace. **Omettre** `avatar_url` demande « ne
      // touche pas » ; l'envoyer à `null` demande « efface ». L'écran qui retire une photo
      // exprime la seconde, et un encodeur qui saute les nuls exprimerait la première —
      // sans erreur, la photo resterait simplement là.
      await Reglages(api: clientQuiCapture()).enregistrerLeProfil(
        nom: 'Clara',
        fuseau: 'Europe/Zurich',
        avatar: null,
      );
      expect(corpsEnvoye.containsKey('avatar_url'), isTrue,
          reason: 'le champ doit être présent');
      expect(corpsEnvoye['avatar_url'], isNull);
    });

    test("l'adresse e-mail ne part pas", () async {
      // La changer demande une vérification que cette route ne déclenche pas. L'envoyer
      // ferait croire qu'on peut la modifier ici.
      await Reglages(api: clientQuiCapture()).enregistrerLeProfil(
        nom: 'Clara',
        fuseau: 'Europe/Zurich',
        avatar: 'https://exemple.ch/photo.png',
      );
      expect(corpsEnvoye.containsKey('email'), isFalse);
      expect(corpsEnvoye['avatar_url'], 'https://exemple.ch/photo.png');
    });
  });

  group('Les rôles', () {
    Membre membre(String role) => Membre.depuisJson(
        {'user_id': 'u', 'name': 'X', 'email': 'x@example.com', 'role': role});

    test('les rôles connus se disent dans les deux langues', () {
      expect(membre('owner').roleLisible(fr), 'Propriétaire');
      expect(membre('admin').roleLisible(fr), 'Administrateur');
      expect(membre('member').roleLisible(fr), 'Membre');
      expect(membre('owner').roleLisible(en), 'Owner');
      expect(membre('member').roleLisible(en), 'Member');
    });

    test("un rôle inconnu s'affiche tel quel", () {
      // Un serveur plus récent peut en introduire. Le masquer, ou le ramener à « membre »,
      // présenterait quelqu'un comme moins puissant qu'il n'est — ce qui est pire que de
      // l'afficher en anglais.
      expect(membre('billing_manager').roleLisible(fr), 'billing_manager');
      expect(membre('billing_manager').roleLisible(en), 'billing_manager');
    });
  });
}
