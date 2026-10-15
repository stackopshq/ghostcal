// Ce que l'application fait d'un **vrai** serveur, depuis iOS.
//
// ─── Pourquoi ce fichier, à côté des cinquante témoins de `test/` ───
//
// `test/photo_et_questions_test.dart` éprouve la forme que le client **envoie**, avec un
// client HTTP feint. C'est utile et borné : il prouve que le mobile est cohérent avec
// l'idée qu'on se fait du serveur, jamais que le serveur l'accepte. Trois nouveautés
// n'avaient jamais traversé la frontière sur iOS — la photo de profil, les questions de
// réservation, et le format `v:1` du cœur commun.
//
// Il lui faut donc `tools/banc-local.sh` allumé, et il le **dit** s'il ne répond pas
// plutôt que d'expirer sur un écran de connexion.
//
// ─── Pourquoi il passe par les services et non par les écrans ───
//
// Les services sont le code que les écrans appellent : `Agenda.creerUnEvenement`,
// `Reglages.televerserLaPhoto`, `TypesDeRendezVous.creer` sont exactement les appels que
// produisent les boutons. Les piloter directement éprouve la même chaîne — jusqu'au
// chiffrement et au serveur — sans dépendre de la position d'un widget, qui change à
// chaque retouche de la charte. Le rendu, lui, est déjà couvert par `captures_test.dart`.
//
// ─── Ce qu'il n'atteint pas, et qu'il ne faut pas compter couvert ───
//
// - **la sélection de la photo** : `image_picker` ouvre `PHPickerViewController`, une vue
//   du système, hors de l'arbre de widgets. `flutter_test` ne peut pas la toucher ; il
//   faudrait XCUITest. Ce qui est éprouvé ici, c'est **ce que cette vue rend** : des
//   octets HEIC bruts sont refusés par le serveur, et c'est la conversion du greffon qui
//   sauve la fonction. La mesurer sur le refus vaut mieux que de l'affirmer ;
// - **Face ID** : le trousseau scellé ne se mesure que sur matériel, et
//   `biometrie_trois_etats_test.dart` s'en charge. Le simulateur relit une entrée scellée
//   en 0 ms, sans invite.

import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:ghostcal/modeles/adresse.dart';
import 'package:ghostcal/services/agenda.dart';
import 'package:ghostcal/services/api.dart';
import 'package:ghostcal/services/auth.dart';
import 'package:ghostcal/services/reglages.dart';
import 'package:ghostcal/services/types_de_rendez_vous.dart';
import 'package:ghostcal/src/rust/frb_generated.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  const serveur = String.fromEnvironment('GHOSTCAL_SERVEUR');
  const email = String.fromEnvironment('GHOSTCAL_EMAIL');
  const phrase = String.fromEnvironment('GHOSTCAL_PHRASE');

  /// Un HEIC véritable, celui que rend un iPhone, en base64.
  ///
  /// Passé par `--dart-define` et non lu sur le disque : le bac à sable de l'application
  /// ne voit pas les fichiers du Mac, et une image déposée dans la photothèque du
  /// simulateur ne s'atteint que par la vue du système, qu'on ne peut pas toucher.
  const heicEnBase64 = String.fromEnvironment('GHOSTCAL_HEIC_B64');

  /// Le **même** HEIC, converti en JPEG par l'hôte : exactement ce que
  /// `UIImageJPEGRepresentation` rend au greffon quand la photothèque livre un HEIC.
  /// Fabriquer une image en Dart éprouverait l'encodeur de Dart, pas ce chemin-là.
  const jpegEnBase64 = String.fromEnvironment('GHOSTCAL_JPEG_B64');

  late ClientAPI api;
  late Auth auth;
  late String organisation;

  setUpAll(() async {
    expect(serveur, isNotEmpty, reason: 'GHOSTCAL_SERVEUR manquant (--dart-define)');
    expect(email, isNotEmpty, reason: 'GHOSTCAL_EMAIL manquant (--dart-define)');
    expect(phrase, isNotEmpty, reason: 'GHOSTCAL_PHRASE manquant (--dart-define)');

    await RustLib.init();

    final base = AdresseDeServeur.normaliser(serveur);
    expect(base, isNotNull, reason: '« $serveur » n\'est pas une adresse acceptable');
    api = ClientAPI(base: base!);
    auth = Auth(api);

    final echec = await auth.seConnecter(email: email, motDePasse: phrase);
    expect(
      echec,
      isNull,
      reason: 'Le coffre ne s\'est pas ouvert sur $serveur. Le banc est-il allumé '
          '(tools/banc-local.sh) ? Raison rendue : $echec',
    );
    expect(auth.estDeverrouille, isTrue);

    organisation = auth.organisations.first;
    api.poserLOrganisation(organisation);
  });

  test('le coffre s\'ouvre par mot de passe contre le vrai serveur', () {
    // Le déverrouillage a eu lieu dans `setUpAll` ; ce témoin le **nomme**, pour qu'un
    // échec se lise comme « le coffre ne s'ouvre pas » et non comme une panne de montage.
    expect(auth.estDeverrouille, isTrue);
    expect(auth.clesDe(organisation), isNotNull);
  });

  test('ce que le client scelle porte la version 1', () async {
    final scelle = await auth.sceller(
      Uint8List.fromList(utf8.encode('{"title":"témoin de version"}')),
      organisation: organisation,
    );
    final enveloppe = jsonDecode(scelle) as Map<String, dynamic>;
    expect(
      enveloppe['v'],
      1,
      reason: 'L\'enveloppe écrite par le mobile doit porter v:1 — c\'est précisément ce '
          'que le web en production ne sait pas encore lire (#176).',
    );
  });

  test('un événement s\'écrit, et se relit en clair', () async {
    final agenda = Agenda(api: api, auth: auth);
    final calendriers = await agenda.calendriers();
    final inscriptible = calendriers.firstWhere(
      (c) => c.inscriptible,
      orElse: () => throw StateError(
        'Aucun calendrier inscriptible sur le compte du banc : rien à écrire.',
      ),
    );

    final titre = 'Témoin iOS ${DateTime.now().microsecondsSinceEpoch}';
    final debut = DateTime.now().add(const Duration(hours: 3));
    final id = await agenda.creerUnEvenement(
      titre: titre,
      debut: debut,
      fin: debut.add(const Duration(minutes: 30)),
      journeeEntiere: false,
      calendrier: inscriptible.id,
      organisation: organisation,
    );
    expect(id, isNotEmpty);

    final lignes = await agenda.lignes(
      de: debut.subtract(const Duration(days: 1)),
      a: debut.add(const Duration(days: 1)),
      organisation: organisation,
    );
    final relue = lignes.where((l) => l.titre == titre);
    expect(
      relue,
      hasLength(1),
      reason: 'L\'événement écrit ne s\'est pas relu : le serveur l\'a pris, et le '
          'déchiffrement a échoué au retour.',
    );
  });

  test('un contenu scellé sous une autre clé s\'affiche, au lieu de disparaître', () async {
    // Le banc d'épreuve en dépose un exprès. Une ligne absente se lirait « libre », ce qui
    // est pire qu'une ligne rouge : elle ferait prendre un créneau déjà pris.
    final agenda = Agenda(api: api, auth: auth);
    final maintenant = DateTime.now();
    final lignes = await agenda.lignes(
      de: maintenant.subtract(const Duration(days: 7)),
      a: maintenant.add(const Duration(days: 14)),
      organisation: organisation,
    );
    expect(
      lignes.where((l) => l.provenance == ProvenanceDuTitre.illisible),
      isNotEmpty,
      reason: 'Le banc d\'épreuve pose un événement scellé sous une autre clé. Sans lui '
          'dans la liste, on ne sait pas si l\'écran l\'afficherait ou l\'avalerait.',
    );
  });

  group('la photo de profil', () {
    // Construit **dans** chaque témoin et non dans le corps du groupe : celui-ci
    // s'évalue à la déclaration, avant `setUpAll`, et `api` n'existe pas encore.
    test('des octets HEIC bruts sont refusés par le serveur', () async {
      final reglages = Reglages(api: api);
      expect(
        heicEnBase64,
        isNotEmpty,
        reason: 'GHOSTCAL_HEIC_B64 manquant (--dart-define)',
      );
      final heic = base64Decode(heicEnBase64);
      // L'en-tête est bien celui d'un HEIC, et non d'un JPEG déguisé : c'est ce qui rend
      // le refus informatif.
      expect(utf8.decode(heic.sublist(4, 12)), 'ftypheic');

      await expectLater(
        reglages.televerserLaPhoto(heic, 'photo.heic'),
        throwsA(anything),
        reason: 'Le serveur n\'accepte que PNG, JPEG, WebP et GIF (application/avatars.py). '
            'Un HEIC passé tel quel doit être refusé — c\'est la conversion de '
            '`image_picker` qui rend la fonction possible, et ce refus le mesure.',
      );
    });

    test('un JPEG est accepté, s\'affiche, puis se retire', () async {
      final reglages = Reglages(api: api);
      expect(
        jpegEnBase64,
        isNotEmpty,
        reason: 'GHOSTCAL_JPEG_B64 manquant (--dart-define)',
      );
      final jpeg = base64Decode(jpegEnBase64);
      expect(jpeg[0], 0xFF, reason: 'Ce doit être un vrai JPEG.');
      await reglages.televerserLaPhoto(jpeg, 'image_picker_temoin.jpg');

      final profil = await reglages.profil();
      // `aUnePhoto`, donc `avatar_updated_at`, et **pas** `avatar_url` : le téléversement
      // écrit les octets dans `users` et ne touche jamais l'URL, qui est l'ancien réglage
      // d'image distante. C'est aussi ce que l'écran regarde pour choisir entre la photo
      // et les initiales.
      expect(
        profil.aUnePhoto,
        isTrue,
        reason: 'Le profil relu doit annoncer la photo que le serveur vient d\'accepter.',
      );

      // Ce que l'écran fait à la réouverture : il va rechercher les octets.
      final octets = await reglages.photo(profil.id);
      expect(octets, isNotEmpty);
      // Le serveur ré-encode en WebP, borné à 256 Kio. Ce n'est pas le JPEG envoyé.
      expect(octets.length, lessThanOrEqualTo(256 * 1024));
      expect(utf8.decode(octets.sublist(0, 4)), 'RIFF');
      expect(utf8.decode(octets.sublist(8, 12)), 'WEBP');

      await reglages.retirerLaPhotoTeleversee();
      final apres = await reglages.profil();
      expect(
        apres.aUnePhoto,
        isFalse,
        reason: 'La photo retirée doit cesser d\'être annoncée.',
      );
    });
  });

  test('une question à choix obligatoire revient telle qu\'elle est partie', () async {
    final service = TypesDeRendezVous(api: api);
    final nom = 'Témoin iOS ${DateTime.now().microsecondsSinceEpoch}';
    final question = {
      'id': 'q1_temoi',
      'label': 'Votre entreprise ?',
      'type': 'select',
      'required': true,
      'options': ['PME', 'Grand groupe'],
    };

    // `title` et non `name` : c'est ainsi que le serveur nomme le champ, et
    // `TypeDeRendezVous.depuisJson` le relit sous ce nom.
    await service.creer({'title': nom, 'questions': [question]});

    final types = await service.lister();
    final cree = types.where((t) => t.titre == nom);
    expect(cree, hasLength(1), reason: 'Le type créé ne figure pas dans la liste.');

    final detail = await service.detail(cree.single.id);
    final revenues = (detail['questions'] as List).cast<Map<String, dynamic>>();
    expect(revenues, hasLength(1));
    // L'identifiant est ce par quoi les réponses sont indexées : le perdre détacherait
    // silencieusement les réponses déjà données de la question qui les a posées.
    expect(revenues.single['id'], 'q1_temoi');
    expect(revenues.single['label'], 'Votre entreprise ?');
    expect(revenues.single['type'], 'select');
    expect(revenues.single['required'], isTrue);
    expect(revenues.single['options'], ['PME', 'Grand groupe']);

    await service.supprimer(cree.single.id);
  });
}
