// Les témoins du **déclenchement automatique**, et de ce qu'on dit quand il échoue.
//
// Ils gardent la leçon la plus chère de GhostPass iOS : un garde « une seule demande par
// présentation » qui se referme sur une question **jamais posée** laisse un bouton mort.
// Le symptôme ne se voit pas en simulateur, parce que le trousseau y répond tout de suite ;
// il faut donc que la distinction soit gardée ici, où l'on peut la provoquer.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/ecrans/connexion.dart';
import 'package:ghostcal/services/biometrie.dart';
import 'package:ghostcal/services/session.dart';
import 'harnais.dart';

/// Un magasin qui répond ce qu'on lui dit de répondre, et qui **compte les questions**.
///
/// Le compte est le cœur du dispositif : « la question est partie seule » n'est pas
/// observable dans l'arbre de widgets, seulement dans le fait que le magasin a été
/// interrogé sans qu'on ait touché quoi que ce soit.
class MagasinFeint extends Biometrie {
  MagasinFeint(
    this._reponses, {
    this.empreinte = Empreinte.visage,
    this.scellee = true,
    this.etatDuSceau,
  });

  /// Ce que rend l'interrogation de **présence**, quand on veut qu'elle diffère de la
  /// simple présence — le cas Android d'une clé invalidée, que le KeyStore signale dès
  /// `containsKey`.
  final Issue? etatDuSceau;

  /// Une réponse par appel. La liste permet de rejouer la vraie séquence d'un lancement :
  /// « pas maintenant », puis la phrase une fois l'application au premier plan.
  final List<Rappel> _reponses;
  final Empreinte? empreinte;
  bool scellee;

  int questions = 0;
  int oublis = 0;

  @override
  Future<Empreinte?> disponible() async => empreinte;

  @override
  Future<Issue> sceau() async =>
      etatDuSceau ?? (scellee ? Issue.ouverte : Issue.absente);

  @override
  Future<Rappel> rappeler() async {
    final reponse = _reponses[questions.clamp(0, _reponses.length - 1)];
    questions++;
    return reponse;
  }

  /// Change ce que rendra la prochaine question, sans toucher au compte.
  ///
  /// Sert aux témoins qui éprouvent le **chemin du bouton** après que le déclenchement
  /// automatique a consommé la liste : sans cela, toucher l'icône rejouerait la dernière
  /// réponse et le témoin mesurerait la fixture au lieu de l'écran.
  void repondre(Rappel r) => _reponses
    ..clear()
    ..add(r);

  @override
  Future<void> oublier() async {
    oublis++;
    scellee = false;
  }

  @override
  Future<bool> retenir(String phrase) async => true;
}

Session sessionReprise() {
  final session = Session()
    ..serveur = 'https://ghostcal.example.com'
    ..email = 'clara@example.com';
  session.debugPoserSessionEnregistree(true);
  return session;
}

/// Déroule la fenêtre d'attente.
///
/// **`pumpAndSettle` ne suffit pas, et c'est un piège d'instrument** : il s'arrête dès
/// qu'aucune image n'est programmée, or un `Future.delayed` n'en programme aucune. Le
/// premier jet de ces témoins mesurait donc un seul essai et « prouvait » que la reprise
/// n'existait pas. Il faut avancer l'horloge explicitement.
Future<void> deroulerLaFenetre(WidgetTester tester) async {
  for (var i = 0; i < 8; i++) {
    await tester.pump(const Duration(milliseconds: 300));
  }
}

Future<MagasinFeint> afficher(
  WidgetTester tester,
  List<Rappel> reponses, {
  Session? session,
  Empreinte? empreinte = Empreinte.visage,
  bool scellee = true,
  Issue? etatDuSceau,
}) async {
  final magasin = MagasinFeint(reponses,
      empreinte: empreinte, scellee: scellee, etatDuSceau: etatDuSceau);
  await tester.pumpWidget(appDEpreuve(
      EcranDeConnexion(session: session ?? sessionReprise(), biometrie: magasin)));
  await tester.pump();
  await deroulerLaFenetre(tester);
  return magasin;
}

void main() {
  group('La question part seule', () {
    /// Le témoin qui manquait : avant ce travail, `rappeler` n'était appelé que depuis
    /// `onPressed`. Il fallait toucher l'icône, et rien ne le signalait.
    testWidgets('sans qu\'on touche l\'icône', (tester) async {
      final magasin = await afficher(tester, [const Rappel(Issue.refusee)]);
      expect(magasin.questions, greaterThan(0),
          reason: 'le magasin n\'a jamais été interrogé : la demande ne part pas seule');
    });

    /// La distinction qui a coûté trois correctifs. « Pas maintenant » n'est pas un refus :
    /// le trousseau n'a rien présenté à personne, et s'arrêter là laisse un bouton mort.
    testWidgets('elle réessaie tant que le trousseau n\'est pas en état de la poser',
        (tester) async {
      final magasin = await afficher(tester, [
        const Rappel(Issue.pasMaintenant),
        const Rappel(Issue.pasMaintenant),
        Rappel(Issue.ouverte, phrase: 'ouvre-toi'),
      ]);
      expect(magasin.questions, 3,
          reason: 'un « pas maintenant » a été pris pour une réponse');
    });

    /// L'autre bord du même piège : réessayer sans borne poserait l'invite en rafale.
    testWidgets('mais elle ne réessaie pas sans fin', (tester) async {
      final magasin = await afficher(tester, [const Rappel(Issue.pasMaintenant)]);
      expect(magasin.questions, lessThanOrEqualTo(4),
          reason: 'une boucle sans borne poserait la biométrie en rafale');
    });

    /// Un refus est une réponse : redemander harcèlerait celle qui vient de dire non.
    testWidgets('un refus referme le garde', (tester) async {
      final magasin = await afficher(tester, [const Rappel(Issue.refusee)]);
      expect(magasin.questions, 1);
    });

    /// Rien de scellé : aucune raison d'aller réveiller le matériel.
    testWidgets('rien ne part si aucune phrase n\'est scellée', (tester) async {
      final magasin = await afficher(tester, [const Rappel(Issue.refusee)], scellee: false);
      expect(magasin.questions, 0);
    });

    /// Une première connexion n'a pas de coffre connu de cet appareil.
    testWidgets('rien ne part sur une première connexion', (tester) async {
      final magasin =
          await afficher(tester, [const Rappel(Issue.refusee)], session: Session());
      expect(magasin.questions, 0);
    });
  });

  group('Ce qui rate se lit à l\'écran', () {
    /// **Le repli silencieux que ce travail visait.** Une entrée invalidée par un nouvel
    /// enrôlement rendait `null`, l'écran retombait sur la saisie, et il ne restait qu'une
    /// icône qui n'ouvrait plus rien — sans un mot pour dire que c'était normal.
    testWidgets('une entrée invalidée le dit, et retire l\'icône', (tester) async {
      final magasin = await afficher(tester, [const Rappel(Issue.invalidee)]);

      expect(find.byKey(const Key('mot.biometrie')), findsOneWidget,
          reason: 'l\'invalidation est muette : rien ne distingue la panne du cas normal');
      expect(find.textContaining('ajoutée ou retirée'), findsOneWidget);
      expect(magasin.oublis, 1,
          reason: 'l\'entrée morte reste en place et échouera à chaque fois');
    });

    /// **Constaté sur émulateur, pas déduit.** Après l'enrôlement d'une empreinte de plus,
    /// le KeyStore lève `KeyPermanentlyInvalidatedException` **dès l'interrogation de
    /// présence**, avant toute lecture. Tant que cette interrogation rendait un `bool`,
    /// l'invalidation se lisait « rien n'a jamais été scellé » : le bouton disparaissait
    /// sans un mot, et le message écrit pour ce cas ne pouvait jamais paraître. La
    /// garantie tenait, et le produit la taisait.
    testWidgets('une clé invalidée dès l\'interrogation de présence se dit', (tester) async {
      final magasin = await afficher(tester, [const Rappel(Issue.refusee)],
          etatDuSceau: Issue.invalidee);

      expect(find.byKey(const Key('mot.biometrie')), findsOneWidget,
          reason: 'l\'invalidation vue à la présence reste muette');
      expect(find.textContaining('ajoutée ou retirée'), findsOneWidget);
      expect(magasin.questions, 0,
          reason: 'inutile de réveiller le matériel pour une clé déjà morte');
    });

    /// Ranger l'inconnu parmi les refus rendrait l'écran muet devant une vraie panne.
    testWidgets('une panne du magasin se nomme', (tester) async {
      await afficher(tester, [const Rappel(Issue.echec, detail: "magasin corrompu")]);
      expect(find.textContaining('magasin corrompu'), findsOneWidget);
    });

    /// Un refus, lui, ne mérite aucun texte : le système vient d'afficher le sien.
    testWidgets('un refus n\'ajoute pas de bruit', (tester) async {
      await afficher(tester, [const Rappel(Issue.refusee)]);
      expect(find.byKey(const Key('mot.biometrie')), findsNothing);
    });
  });

  /// ─── Le troisième état, celui qu'on ne voyait pas ───
  ///
  /// Vert, rouge, et **« je n'ai pas pu regarder »**. Les deux premiers étaient traités ;
  /// le troisième était reconnu par le classement, puis perdu à l'écran : le garde se
  /// rouvrait, et rien ne paraissait. Or c'est exactement ce que voit quelqu'un dont la
  /// biométrie a cessé de se lancer — un écran parfaitement normal.
  ///
  /// Ces témoins gardent les deux moitiés : que ça se **dise**, et que ça ne **boucle**
  /// pas. Une panne bruyante n'est pas un progrès sur une panne muette.
  group('« Je n\'ai pas pu regarder » se dit, et ne boucle pas', () {
    testWidgets('quatre « pas maintenant » d\'affilée le disent', (tester) async {
      await afficher(tester, [const Rappel(Issue.pasMaintenant)]);

      expect(find.byKey(const Key('mot.biometrie')), findsOneWidget,
          reason: 'la question n\'a jamais été posée, et l\'écran n\'en dit rien : '
              'c\'est la panne muette du 2026-09-25');
      expect(find.textContaining('n\'était pas en état de présenter'), findsOneWidget);
    });

    /// Le mot ne doit rien affirmer de cassé : le sceau est intact, et dire le contraire
    /// enverrait retaper une phrase pour rien.
    testWidgets('il ne parle ni d\'invalidation ni d\'effacement', (tester) async {
      final magasin = await afficher(tester, [const Rappel(Issue.pasMaintenant)]);
      expect(find.textContaining('ajoutée ou retirée'), findsNothing);
      expect(magasin.oublis, 0, reason: 'un sceau intact vient d\'être effacé');
    });

    /// **La borne.** La première correction de GhostPass réessayait sans fin et faisait
    /// clignoter le bouton. Dérouler largement la fenêtre ne doit pas relancer la question
    /// au-delà des quatre essais prévus.
    testWidgets('dire ne relance pas la question', (tester) async {
      final magasin = await afficher(tester, [const Rappel(Issue.pasMaintenant)]);
      final apresLaFenetre = magasin.questions;
      for (var i = 0; i < 40; i++) {
        await tester.pump(const Duration(milliseconds: 300));
      }
      expect(magasin.questions, apresLaFenetre,
          reason: 'la question repart toute seule : la panne muette a été remplacée par '
              'une panne bruyante');
      expect(apresLaFenetre, lessThanOrEqualTo(4));
    });

    /// Le bouton est le seul chemin qui reste, et il doit rester vivant.
    testWidgets('le bouton reste offert', (tester) async {
      await afficher(tester, [const Rappel(Issue.pasMaintenant)]);
      expect(find.byType(OutlinedButton), findsOneWidget,
          reason: 'sans icône ni message, il ne reste plus aucune issue');
    });

    /// Le chemin du bouton tombe dans le même cas quand l'application n'est pas active.
    /// Sans message, toucher l'icône ne produit **rien du tout** — le bouton mort.
    testWidgets('toucher l\'icône sans pouvoir demander se dit aussi', (tester) async {
      final magasin = await afficher(tester, [const Rappel(Issue.refusee)]);
      expect(find.byKey(const Key('mot.biometrie')), findsNothing);

      magasin.repondre(const Rappel(Issue.pasMaintenant));
      await tester.tap(find.byType(OutlinedButton));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('mot.biometrie')), findsOneWidget,
          reason: 'l\'icône a été touchée, rien ne s\'est passé, et rien ne le dit');
    });

    /// Un « je n'ai pas pu demander » qui survit à une question aboutie est un mensonge de
    /// plus. Ce qui le remplace peut être autre chose — ici la phrase scellée est bien
    /// relue mais n'ouvre pas le coffre de ce témoin, et l'écran le dit. Ce qui compte est
    /// qu'il ne dise plus l'**ancienne** cause.
    testWidgets('le mot ne survit pas à une question aboutie', (tester) async {
      final magasin = await afficher(tester, [const Rappel(Issue.pasMaintenant)]);
      expect(find.textContaining('n\'était pas en état de présenter'), findsOneWidget);

      magasin.repondre(Rappel(Issue.ouverte, phrase: 'ouvre-toi'));
      // Le message pousse le bouton hors du cadre du témoin ; sans ce défilement, le
      // `tap` manque sa cible et ne produit qu'un avertissement. Le témoin « passerait »
      // alors sans avoir rien touché, ce qui est le vert le plus dangereux.
      await tester.ensureVisible(find.byType(OutlinedButton));
      await tester.tap(find.byType(OutlinedButton));
      await tester.pumpAndSettle();

      expect(find.textContaining('n\'était pas en état de présenter'), findsNothing,
          reason: 'la question a fini par être posée, et l\'écran affiche encore '
              'qu\'elle ne l\'a pas été');
    });
  });

  group('Le classement des pannes de plateforme', () {
    /// La confusion fondatrice : `interactionNotAllowed` **n'est pas** un refus.
    test('interactionNotAllowed n\'est pas un refus', () {
      expect(
        Biometrie.classerPourTemoin(
            PlatformException(code: 'Unexpected security result code', details: -25308)),
        Issue.pasMaintenant,
      );
    });

    test('un refus de l\'utilisateur est un refus', () {
      expect(
        Biometrie.classerPourTemoin(
            PlatformException(code: 'Unexpected security result code', details: -128)),
        Issue.refusee,
      );
    });

    /// **Le message que le paquet envoie réellement**, relevé sur émulateur après avoir
    /// enrôlé une empreinte de plus. `flutter_secure_storage` 11 attrape la
    /// `KeyPermanentlyInvalidatedException` et la remplace par une exception de son cru :
    /// le nom de la classe n'atteint jamais Dart — vérifié, `details` fait 2073 octets et
    /// ne le contient nulle part. Il ne reste que ce texte.
    ///
    /// Ce témoin existe pour que la chaîne, si elle change à la prochaine montée de
    /// version, tombe ici plutôt que chez quelqu'un dont le bouton biométrique affiche
    /// une trace Java.
    test('le message réel du paquet Android vaut invalidation', () {
      expect(
        Biometrie.classerPourTemoin(PlatformException(
          code: 'Exception encountered',
          message: 'Migration failed after algorithm change '
              '(Invalid key, key type incompatible with cipher). '
              'Enable resetOnError=true or call deleteAll().',
        )),
        Issue.invalidee,
      );
    });

    /// Android signale l'invalidation par le nom de sa classe d'exception.
    test('une clé invalidée par un nouvel enrôlement se reconnaît', () {
      expect(
        Biometrie.classerPourTemoin(PlatformException(
          code: 'Exception encountered',
          message: 'android.security.keystore.KeyPermanentlyInvalidatedException',
        )),
        Issue.invalidee,
      );
    });

    /// **La règle qui garde l'instrument honnête.** Ce qu'on ne sait pas classer ne doit
    /// jamais devenir un refus : un refus est muet, et une panne muette ne se corrige pas.
    test('ce qu\'on ne sait pas classer ne devient pas un refus', () {
      final issue = Biometrie.classerPourTemoin(
          PlatformException(code: 'Exception encountered', message: 'quelque chose de neuf'));
      expect(issue, Issue.echec);
      expect(issue, isNot(Issue.refusee));
    });
  });
}
