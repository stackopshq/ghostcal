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

/// Un magasin qui répond ce qu'on lui dit de répondre, et qui **compte les questions**.
///
/// Le compte est le cœur du dispositif : « la question est partie seule » n'est pas
/// observable dans l'arbre de widgets, seulement dans le fait que le magasin a été
/// interrogé sans qu'on ait touché quoi que ce soit.
class MagasinFeint extends Biometrie {
  MagasinFeint(this._reponses, {this.empreinte = Empreinte.visage, this.scellee = true});

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
  Future<bool> aUnePhrase() async => scellee;

  @override
  Future<Rappel> rappeler() async {
    final reponse = _reponses[questions.clamp(0, _reponses.length - 1)];
    questions++;
    return reponse;
  }

  @override
  Future<void> oublier() async {
    oublis++;
    scellee = false;
  }

  @override
  Future<void> retenir(String phrase) async {}
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
}) async {
  final magasin = MagasinFeint(reponses, empreinte: empreinte, scellee: scellee);
  await tester.pumpWidget(MaterialApp(
    home: EcranDeConnexion(session: session ?? sessionReprise(), biometrie: magasin),
  ));
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
