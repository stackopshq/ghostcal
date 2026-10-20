import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:ghostcal/main.dart';
import 'package:ghostcal/services/agenda.dart';
import 'package:ghostcal/services/biometrie.dart';
import 'package:ghostcal/services/rappels.dart';
import 'package:ghostcal/services/reglages.dart';
import 'package:ghostcal/services/session.dart';
import 'package:ghostcal/services/types_de_rendez_vous.dart';
import 'package:ghostcal/services/verrouillage.dart';
import 'package:ghostcal/services/vignette.dart';
import 'package:ghostcal/src/rust/frb_generated.dart';

/// Ce que seule la machine peut dire de la version macOS.
///
///     ./tools/banc-local.sh                       # dans une autre fenêtre
///     flutter test integration_test/macos_test.dart -d macos \
///       --dart-define=GHOSTCAL_SERVEUR=127.0.0.1:8099 \
///       --dart-define=GHOSTCAL_EMAIL=clara@example.com \
///       --dart-define=GHOSTCAL_PHRASE=… \
///       --dart-define=GHOSTCAL_HEIC=<base64 d'une photo HEIC>
///
/// ─── Pourquoi ce fichier existe à côté des 217 témoins hors matériel ───
///
/// Aucun d'eux ne touche un trousseau, un décodeur d'image du système, ni un serveur.
/// Ils prouvent que le client est cohérent avec l'idée qu'on se fait de ses plateformes.
/// Or tout ce que le portage macOS a cassé était précisément de cet ordre : des options
/// posées sur `iOptions`, que macOS ne lit pas ; un redimensionnement qu'`image_picker`
/// annonce et n'exécute pas ici. Des réglages justes en apparence, et sans effet.
///
/// ─── Ce qu'il ne peut pas faire, et qu'il ne prétend pas faire ───
///
/// **Toucher le capteur.** Touch ID demande un doigt, et aucun appareil réel ne le simule
/// — c'est le propre d'une biométrie. Ce qui est éprouvé ici, c'est tout ce qui mène au
/// capteur : que l'écriture sous contrainte matérielle réussisse (donc que le groupe
/// d'accès au trousseau soit accordé), et que l'interrogation de présence réponde sans
/// rien présenter. L'invite elle-même reste à constater à la main.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  const serveur = String.fromEnvironment('GHOSTCAL_SERVEUR');
  const email = String.fromEnvironment('GHOSTCAL_EMAIL');
  const phrase = String.fromEnvironment('GHOSTCAL_PHRASE');
  const heic = String.fromEnvironment('GHOSTCAL_HEIC');

  /// Où les captures atterrissent.
  ///
  /// `systemTemp` et non un chemin choisi : l'application est en bac à sable, et le seul
  /// dossier où elle écrit sans droit supplémentaire est le `tmp` de son conteneur. Du
  /// Mac, il se lit sous `~/Library/Containers/ch.stackops.ghostcal/Data/tmp`.
  final sorties = Directory('${Directory.systemTemp.path}/ghostcal-macos');

  /// Recracher les captures sur la sortie du test, en base64.
  ///
  /// Le détour n'est pas une coquetterie. L'application est en bac à sable : le seul
  /// dossier où elle écrit est celui de son conteneur, et macOS **protège** le conteneur
  /// d'une application contre les autres processus. Un terminal sans « accès complet au
  /// disque » reçoit « Operation not permitted » sur le dossier qu'il vient de faire
  /// remplir. Les deux moitiés sont justes séparément, et ensemble elles produisent des
  /// images qu'on ne peut pas regarder.
  ///
  /// `GHOSTCAL_CAPTURES_SORTIE=1` les fait donc sortir par le seul canal qui traverse le
  /// bac à sable : stdout. `tools/macos/extraire-captures.py` les recompose.
  const parStdout = bool.fromEnvironment('GHOSTCAL_CAPTURES_SORTIE');

  final cle = GlobalKey();

  Future<void> photographier(WidgetTester tester, String nom) async {
    await tester.pumpAndSettle();
    // Laisser la composition finir. `pumpAndSettle` rend la main dès que l'arbre est
    // stable ; une transition encore en cours donnerait une image à demi opaque, qui
    // passe tous les contrôles automatiques et ne se voit qu'à l'œil.
    await Future<void>.delayed(const Duration(milliseconds: 600));
    // `pump` et non `pumpAndSettle` : après un délai réel, le second ne rend jamais la
    // main sur macOS — le curseur d'un champ de saisie clignote, donc une image est
    // toujours demandée, donc rien n'est jamais « stabilisé ». Le test expire au bout de
    // trois minutes sur une assertion qui parle d'images en attente et pas de curseur.
    await tester.pump();
    final boite = cle.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    // ─── `toImageSync`, et c'est tout le sujet de cette fonction ───
    //
    // `toImage` rend un `Future` que le moteur complète à l'image suivante. Dans un test
    // d'intégration, cette image-là n'arrive jamais : le harnais tient la boucle, et
    // l'attente ne rend pas la main — même enveloppée dans `runAsync`. Mesuré deux fois :
    // trois minutes de silence sur la première prise de vue, puis une assertion
    // « !_expectingFrame » qui ne nomme ni la capture ni la cause, et qui emporte tous
    // les témoins suivants.
    //
    // `toImageSync` prend l'instantané de la couche **déjà composée**, sans rien attendre.
    // Seule la conversion en PNG reste asynchrone, et elle, c'est du décodage : elle se
    // termine sous `runAsync`.
    final image = boite.toImageSync(pixelRatio: 2);
    final octets = await tester.runAsync(() async =>
        (await image.toByteData(format: ui.ImageByteFormat.png))!.buffer.asUint8List());
    sorties.createSync(recursive: true);
    File('${sorties.path}/$nom.png').writeAsBytesSync(octets!);
    if (parStdout) {
      // ignore_for_file: avoid_print — stdout **est** le transport ici, voir plus haut.
      // Par morceaux : `print` d'une seule ligne de plusieurs centaines de milliers de
      // caractères se fait tronquer en chemin, et une image tronquée ne s'ouvre pas — ce
      // qui se lit comme un défaut du rendu plutôt que du transport.
      final texte = base64Encode(octets);
      print('<<<CAPTURE $nom ${texte.length}');
      for (var i = 0; i < texte.length; i += 720) {
        print(texte.substring(i, i + 720 > texte.length ? texte.length : i + 720));
      }
      print('CAPTURE>>>');
    }
  }

  /// Monte l'application pour de bon, dans une langue, un thème et une fenêtre donnés.
  Future<Session> monter(
    WidgetTester tester, {
    required Locale langue,
    Brightness theme = Brightness.light,
    Size fenetre = const Size(1100, 760),
  }) async {
    tester.view.devicePixelRatio = 2;
    tester.view.physicalSize = fenetre * 2;
    tester.platformDispatcher.platformBrightnessTestValue = theme;
    addTearDown(tester.view.reset);
    addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);

    final session = Session();
    await session.amorcer();
    final verrouillage = Verrouillage();
    await verrouillage.amorcer();
    final rappels = Rappels();
    await rappels.amorcer();
    await tester.pumpWidget(RepaintBoundary(
      key: cle,
      child: GhostcalApp(
        session: session,
        verrouillage: verrouillage,
        locale: langue,
        rappels: rappels,
      ),
    ));
    await tester.pumpAndSettle();
    return session;
  }

  /// Remplit l'écran d'entrée et attend l'agenda. **Échoue** s'il ne vient pas :
  /// continuer photographierait un écran de connexion en croyant tenir le produit.
  ///
  /// ─── Pourquoi ça s'y reprend à deux fois ───
  ///
  /// Le trousseau survit au banc. Après un `banc-local.sh`, les jetons gardés désignent
  /// un compte qui n'existe plus : l'écran montre son visage « reprise » — la phrase
  /// seule —, la reprise échoue sur une session expirée, et l'écran bascule alors sur ses
  /// trois champs. Un témoin qui ne remplit qu'une fois attend là quarante secondes et
  /// accuse le banc.
  ///
  /// On resoumet donc quand l'adresse du serveur **apparaît** : c'est le signal que la
  /// reprise a échoué et que l'écran demande tout.
  Future<void> ouvrirLeCoffre(WidgetTester tester) async {
    Future<void> soumettre() async {
      for (final (cle, valeur) in [
        ('champ.serveur', serveur),
        ('champ.email', email),
        ('champ.phrase', phrase),
      ]) {
        final champ = find.byKey(Key(cle));
        if (champ.evaluate().isNotEmpty) await tester.enterText(champ, valeur);
      }
      await tester.pumpAndSettle();
      await tester.testTextInput.receiveAction(TextInputAction.done);
    }

    var toutDemande = find.byKey(const Key('champ.serveur')).evaluate().isNotEmpty;
    await soumettre();

    final limite = DateTime.now().add(const Duration(seconds: 60));
    while (find.byType(NavigationBar).evaluate().isEmpty) {
      if (DateTime.now().isAfter(limite)) {
        fail('Le coffre ne s\'est pas ouvert en 60 s sur $serveur. Le banc tourne-t-il ?');
      }
      final maintenantTout =
          find.byKey(const Key('champ.serveur')).evaluate().isNotEmpty;
      if (maintenantTout && !toutDemande) {
        // La session enregistrée vient d'être refusée : l'écran demande tout, on redonne
        // tout. Une seule fois — la bascule ne se produit qu'une fois.
        toutDemande = true;
        await soumettre();
      }
      await tester.pump(const Duration(milliseconds: 250));
      await Future<void>.delayed(const Duration(milliseconds: 250));
    }
    await tester.pumpAndSettle();
  }

  /// Attend qu'un libellé paraisse, puis rend la main.
  ///
  /// `pumpAndSettle` ne suffit pas : il rend la main dès que l'arbre est stable, et
  /// l'agenda, lui, attend encore le serveur. Affirmer à cet instant mesure la vitesse du
  /// réseau, pas l'application — et le témoin rougit un jour sur deux, en accusant la
  /// chose qu'il prétend garder.
  Future<void> attendre(WidgetTester tester, Finder quoi, String raison) async {
    final limite = DateTime.now().add(const Duration(seconds: 20));
    while (quoi.evaluate().isEmpty) {
      if (DateTime.now().isAfter(limite)) fail(raison);
      await tester.pump(const Duration(milliseconds: 250));
      await Future<void>.delayed(const Duration(milliseconds: 250));
    }
    await tester.pumpAndSettle();
  }

  setUpAll(() async {
    for (final (nom, valeur) in [
      ('GHOSTCAL_SERVEUR', serveur),
      ('GHOSTCAL_EMAIL', email),
      ('GHOSTCAL_PHRASE', phrase),
      ('GHOSTCAL_HEIC', heic),
    ]) {
      expect(valeur, isNotEmpty, reason: '$nom manquant (--dart-define)');
    }
    await RustLib.init();
    if (sorties.existsSync()) sorties.deleteSync(recursive: true);
  });

  testWidgets('le coffre s\'ouvre à la phrase, et l\'agenda lit les deux formats',
      (tester) async {
    final session = await monter(tester, langue: const Locale('fr'));
    await photographier(tester, '01-entree-fr-clair');
    await ouvrirLeCoffre(tester);
    await photographier(tester, '02-agenda-fr-clair-large');

    // ─── L'enveloppe d'avant la migration ───
    //
    // Déposée par `enveloppe-heritee.py` : AES-256-GCM, nonce de 12 octets, pas de `v`.
    // Elle doit s'**ouvrir**. Si le cœur ne la lisait pas, la ligne ne disparaîtrait pas
    // pour autant : elle s'afficherait « Contenu illisible », ce qui se distingue mal
    // d'un succès quand on ne regarde que le nombre de lignes.
    await tester.tap(find.text('Liste'));
    await tester.pumpAndSettle();
    // ─── Quand ce témoin rougit, il doit dire laquelle des deux choses a manqué ───
    //
    // L'enveloppe héritée est **déposée à la main** : le cœur ne sait plus en écrire, il
    // ne sait que les lire. Tout `banc-local.sh` repart d'une base vide et l'emporte, et
    // le témoin échouait alors sur « Found 0 widgets » — un message qui accuse
    // l'application pour un banc qu'on vient de reconstruire. Vu une fois, cherché
    // longtemps.
    await attendre(
      tester,
      find.text('Web avant migration'),
      'soit une enveloppe sans marqueur de version ne s\'ouvre plus — le vrai défaut —, '
          'soit le banc a été réamorcé depuis et ne la porte plus : '
          '`uv run python tools/enveloppe-heritee.py` la redépose',
    );
    // Et l'inverse se dit par le titre lui-même : une enveloppe que le cœur n'ouvre pas
    // ne disparaît pas de la liste, elle s'affiche « Contenu illisible — clé manquante ».
    // Trouver le titre, c'est donc avoir mesuré les deux.
    //
    // On ne compte **pas** les lignes illisibles. Le banc en dépose une exprès, mais elle
    // vieillit comme toute donnée amorcée : hier elle était dans la fenêtre, aujourd'hui
    // non, et le témoin rougissait pour l'âge du banc plutôt que pour l'application.

    // ─── Ce que l'application écrit, elle, porte le marqueur ───
    //
    // Mesuré sur les octets rendus par le serveur, et non sur ce qu'on croit avoir
    // envoyé : c'est la seule forme qui compte, celle que le web devra relire.
    final api = session.api!;
    final agenda = Agenda(api: api, auth: session.auth!);
    // L'identifiant rendu à la création, et non une différence entre deux listes : les
    // lignes d'agenda développent les récurrences et ne portent pas toutes l'identifiant
    // d'un événement. Les comparer donnait « Bad state: No element », ce qui ne dit rien
    // de ce qu'on cherchait à mesurer.
    // Le titre porte l'heure : le témoin se rejoue, et deux exécutions laisseraient deux
    // lignes du même nom — `hasLength(1)` échouerait pour une raison qui n'a rien à voir
    // avec ce qu'il mesure.
    final titre = 'Écrit par le Mac ${DateTime.now().millisecondsSinceEpoch}';
    final id = await agenda.creerUnEvenement(
      calendrier: (await agenda.calendriers()).firstWhere((c) => c.inscriptible).id,
      debut: DateTime.now().add(const Duration(hours: 6)),
      fin: DateTime.now().add(const Duration(hours: 7)),
      titre: titre,
      description: '',
      lieu: 'Genève',
      journeeEntiere: false,
      organisation: session.organisation!,
    );
    final brut = await api.obtenir<Map<String, dynamic>>('v1/me/calendar/events/$id');
    final enveloppe = jsonDecode('${brut['content']}') as Map<String, dynamic>;
    expect(enveloppe['v'], 1, reason: 'le web ne relira pas une enveloppe sans version');

    // Et il se relit par l'application elle-même, au bon titre : une enveloppe bien
    // formée que le cœur n'ouvrirait pas passerait le contrôle ci-dessus.
    await tester.tap(find.text('Jour'));
    await tester.pumpAndSettle();
    final lignes = await agenda.lignes(
      de: DateTime.now().subtract(const Duration(hours: 1)),
      a: DateTime.now().add(const Duration(hours: 48)),
      organisation: session.organisation!,
    );
    expect(lignes.where((l) => l.titre == titre), hasLength(1),
        reason: 'l\'application ne relit pas ce qu\'elle vient d\'écrire');
  }, timeout: const Timeout(Duration(minutes: 3)));

  testWidgets('une question à choix obligatoire s\'enregistre et se relit', (tester) async {
    final session = await monter(tester, langue: const Locale('fr'));
    await ouvrirLeCoffre(tester);

    final types = TypesDeRendezVous(api: session.api!);
    final titre = 'Entretien macOS ${DateTime.now().millisecondsSinceEpoch}';
    await types.creer({
      'title': titre,
      'duration_min': 45,
      'location_type': 'phone',
      'questions': [
        {
          'id': 'q1',
          'label': 'Quel sujet ?',
          'type': 'select',
          'required': true,
          'options': ['Devis', 'Support', 'Autre'],
        }
      ],
    });

    final relu = await types.detail(
        (await types.lister()).firstWhere((t) => t.titre == titre).id);
    final question = (relu['questions'] as List).single as Map<String, dynamic>;
    expect(question['type'], 'select');
    expect(question['required'], isTrue, reason: 'le caractère obligatoire s\'est perdu');
    expect(question['options'], ['Devis', 'Support', 'Autre']);

    await tester.tap(find.text('RDV'));
    await tester.pumpAndSettle();
    await photographier(tester, '03-rdv-fr-clair');
  }, timeout: const Timeout(Duration(minutes: 3)));

  testWidgets('une photo HEIC devient un JPEG que le serveur accepte', (tester) async {
    final session = await monter(tester, langue: const Locale('fr'));
    await ouvrirLeCoffre(tester);

    // Le fichier est écrit dans le conteneur : hors de lui, le bac à sable refuserait la
    // lecture, et l'échec ressemblerait à un défaut du décodage.
    final source = File('${Directory.systemTemp.path}/portrait.heic')
      ..writeAsBytesSync(base64Decode(heic));
    expect(source.readAsBytesSync().sublist(4, 8), utf8.encode('ftyp'),
        reason: 'la source doit bien être un HEIC');

    const vignette = Vignette();
    final jpeg = await vignette.reduire(source.path);
    expect(jpeg, isNotNull, reason: 'le canal natif n\'a pas répondu');
    expect(jpeg!.sublist(0, 3), [0xFF, 0xD8, 0xFF], reason: 'ce n\'est pas du JPEG');

    final decodee = await ui.instantiateImageCodec(jpeg);
    final image = (await decodee.getNextFrame()).image;
    expect(image.width, lessThanOrEqualTo(1024));
    expect(image.height, lessThanOrEqualTo(1024));

    final reglages = Reglages(api: session.api!);
    await reglages.televerserLaPhoto(jpeg, 'portrait.jpg');
    expect((await reglages.profil()).aUnePhoto, isTrue);
    // Relue depuis le serveur, c'est-à-dire après le ré-encodage en WebP : une photo qui
    // part sans revenir s'afficherait quand même, depuis les octets gardés à l'écran.
    expect(await reglages.photo((await reglages.profil()).id), isNotEmpty);

    await reglages.retirerLaPhotoTeleversee();
    expect((await reglages.profil()).aUnePhoto, isFalse);
  }, timeout: const Timeout(Duration(minutes: 3)));

  testWidgets('le trousseau accepte une phrase sous contrainte matérielle', (tester) async {
    await monter(tester, langue: const Locale('fr'));
    final biometrie = Biometrie();

    // Ce que cette ligne prouve vraiment : `SecItemAdd` a accepté une entrée du trousseau
    // de protection des données, sous contrôle d'accès biométrique. Sans
    // `keychain-access-groups` dans les droits, elle rendrait errSecMissingEntitlement et
    // `retenir` répondrait `false` — en silence, puisqu'il ne jette pas.
    expect(await biometrie.retenir('phrase d\'épreuve'), isTrue,
        reason: 'le groupe d\'accès au trousseau n\'est pas accordé');

    // Et l'interrogation de présence répond **sans présenter Touch ID** : sous
    // `kSecUseAuthenticationUIFail`, le trousseau refuse de demander plutôt que de
    // demander. Un test qui prendrait plus de quelques secondes ici serait le symptôme.
    final depart = DateTime.now();
    expect(await biometrie.sceau(), Issue.ouverte);
    expect(DateTime.now().difference(depart).inSeconds, lessThan(3),
        reason: 'une invite s\'est présentée : le drapeau muet n\'a pas pris');

    await biometrie.oublier();
    expect(await biometrie.sceau(), Issue.absente);
  }, timeout: const Timeout(Duration(minutes: 2)));

  /// ─── L'inscription aux ouvertures de session ───
  ///
  /// Les bannières passent par `flutter_local_notifications`, éprouvé chez lui. Ce qui
  /// reste propre à ce portage est `SMAppService`, et c'était le point qui pouvait échouer
  /// en silence : une application en bac à sable, lancée depuis un dossier de
  /// construction, n'a aucune garantie d'être acceptée, et un refus laisserait un
  /// interrupteur mort dans les réglages.
  ///
  /// Le témoin **remet la machine comme il l'a trouvée** : il n'a pas à laisser une entrée
  /// dans les Réglages Système de qui l'exécute.
  testWidgets('macOS accepte d\'ouvrir GhostCal à la session', (tester) async {
    await monter(tester, langue: const Locale('fr'));
    const canal = MethodChannel(Rappels.canalMacos);

    final depart = await canal.invokeMethod<bool>('lanceALOuvertureDeSession') ?? false;
    try {
      expect(
        await canal.invokeMethod<bool>('lancerALOuvertureDeSession', {'valeur': true}),
        isTrue,
        reason: 'macOS a refusé : le réglage serait un interrupteur mort',
      );
      expect(await canal.invokeMethod<bool>('lanceALOuvertureDeSession'), isTrue,
          reason: 'l\'état n\'est pas relu auprès du système');
    } finally {
      await canal.invokeMethod<bool>('lancerALOuvertureDeSession', {'valeur': depart});
    }
    expect(await canal.invokeMethod<bool>('lanceALOuvertureDeSession'), depart,
        reason: 'le témoin a laissé la machine autrement qu\'il l\'a trouvée');
  }, timeout: const Timeout(Duration(minutes: 2)));

  testWidgets('sombre, anglais, et une petite fenêtre', (tester) async {
    await monter(tester,
        langue: const Locale('en'), theme: Brightness.dark, fenetre: const Size(720, 560));
    await photographier(tester, '04-entree-en-sombre-petite');
    await ouvrirLeCoffre(tester);
    expect(find.text('Calendar'), findsOneWidget, reason: 'les onglets sont restés en français');
    await photographier(tester, '05-agenda-en-sombre-petite');

    await tester.tap(find.text('Settings'));
    await tester.pumpAndSettle();
    await photographier(tester, '06-reglages-en-sombre-petite');
  }, timeout: const Timeout(Duration(minutes: 3)));

  testWidgets('la semaine, en grand et en clair', (tester) async {
    await monter(tester, langue: const Locale('fr'), fenetre: const Size(1440, 900));
    await ouvrirLeCoffre(tester);
    await tester.tap(find.text('Semaine'));
    await tester.pumpAndSettle();
    await photographier(tester, '07-semaine-fr-clair-tres-large');

    await tester.tap(find.text('Mois'));
    await tester.pumpAndSettle();
    await photographier(tester, '08-mois-fr-clair-tres-large');
  }, timeout: const Timeout(Duration(minutes: 3)));
}

