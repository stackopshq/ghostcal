// Ce que les réglages disent du sceau biométrique — et ce qu'ils permettent d'en faire.
//
// ─── Pourquoi ce fichier existe ───
//
// La charte mobile, §0 : « le trousseau rend trois réponses, jamais deux ». La règle vaut
// pour l'écran d'entrée, où elle est gardée par `biometrie_auto_test.dart`. Elle vaut
// **aussi** ici, et c'est ici qu'elle avait été perdue chez GhostPass le 2026-09-25 : le
// réglage restait affiché comme actif alors que le trousseau n'avait plus rien. Un
// interrupteur à deux positions ne peut pas dire « je n'ai pas pu regarder ».
//
// Et la seconde moitié : un enrôlement qu'on ne peut pas retirer n'est pas un réglage,
// c'est une décision définitive prise en cochant une case.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/ecrans/reglages.dart';
import 'package:ghostcal/l10n/generated/app_localisations.dart';
import 'package:ghostcal/services/biometrie.dart';
import 'package:ghostcal/services/session.dart';
import 'package:ghostcal/services/verrouillage.dart' as v;
import 'harnais.dart';

final fr = lookupL(const Locale('fr'));

/// Un magasin qui rend l'état qu'on lui dit de rendre, et qui **compte les questions**.
///
/// Il ne s'appuie volontairement sur aucun vrai trousseau : monter l'écran des réglages
/// avec le magasin de production ferait, sur un appareil, surgir une invite biométrique à
/// l'ouverture des réglages — le défaut même qu'on cherche à interdire.
class SceauFeint extends Biometrie {
  SceauFeint(this.etat, {this.empreinte = Empreinte.visage});

  Issue etat;
  final Empreinte? empreinte;

  int lectures = 0;
  int oublis = 0;
  int questions = 0;

  @override
  Future<Empreinte?> disponible() async => empreinte;

  @override
  Future<Issue> sceau() async {
    lectures++;
    return etat;
  }

  /// Si ceci est appelé, l'écran a demandé la **valeur** et non la présence : sur un
  /// appareil, cela aurait posé le visage devant quelqu'un venu changer un délai.
  @override
  Future<Rappel> rappeler() async {
    questions++;
    return const Rappel(Issue.refusee);
  }

  @override
  Future<void> oublier() async {
    oublis++;
    etat = Issue.absente;
  }
}

Future<SceauFeint> ouvrirLesReglages(
  WidgetTester tester,
  Issue etat, {
  Empreinte? empreinte = Empreinte.visage,
}) async {
  final magasin = SceauFeint(etat, empreinte: empreinte);
  await tester.pumpWidget(appDEpreuve(EcranDeReglages(
    session: Session(),
    verrouillage: v.Verrouillage(),
    biometrie: magasin,
  )));
  // Pas de `pumpAndSettle` : deux sections sans serveur animent un
  // `LinearProgressIndicator` qui ne s'arrête jamais, et l'attente expirerait sans
  // qu'aucune faute ne soit en cause. On avance d'images comptées.
  await tester.pump();
  await tester.pump();
  return magasin;
}

Future<void> montrerLeSceau(WidgetTester tester) async {
  await tester.ensureVisible(find.byKey(const Key('ligne.sceau')));
  await tester.pump();
}

void main() {
  /// **Le cœur du fichier.** Quatre états du magasin, quatre phrases distinctes. Si deux
  /// d'entre elles se confondaient, l'écran serait revenu à l'interrupteur binaire.
  group('Les trois réponses se lisent, et ne se confondent pas', () {
    final attendu = <Issue, String>{
      Issue.ouverte: fr.sceauPose(Empreinte.visage.nom(fr)),
      Issue.absente: fr.sceauAbsent,
      Issue.invalidee: fr.sceauInvalide,
      Issue.echec: fr.sceauIndetermine,
    };

    for (final entree in attendu.entries) {
      testWidgets('${entree.key.name} se dit', (tester) async {
        await ouvrirLesReglages(tester, entree.key);
        await montrerLeSceau(tester);
        expect(find.text(entree.value), findsOneWidget);
      });
    }

    /// **Le troisième état, jusque dans les réglages.** Un magasin qui n'a pas répondu ne
    /// doit surtout pas se peindre « rien n'est scellé » : c'est la formulation qui a
    /// laissé GhostPass afficher un réglage faux pendant une journée.
    testWidgets('« je n\'ai pas pu regarder » n\'est pas « rien n\'est scellé »',
        (tester) async {
      await ouvrirLesReglages(tester, Issue.echec);
      await montrerLeSceau(tester);
      expect(find.text(fr.sceauIndetermine), findsOneWidget);
      expect(find.text(fr.sceauAbsent), findsNothing);
    });

    /// Les quatre phrases sont bien quatre. Sans ce contrôle, le groupe ci-dessus
    /// resterait vert le jour où deux clés pointeraient sur le même texte.
    test('les quatre phrases sont distinctes', () {
      expect(attendu.values.toSet().length, attendu.length);
    });

    testWidgets('sans matériel, la ligne le dit plutôt que de mentir', (tester) async {
      await ouvrirLesReglages(tester, Issue.absente, empreinte: null);
      await montrerLeSceau(tester);
      expect(find.text(fr.sansBiometrieSurCetAppareil), findsOneWidget);
    });
  });

  group('Le retrait', () {
    /// « On doit pouvoir le retirer. » Avant ce travail il n'existait **aucun** chemin
    /// pour le faire : cocher la case au déverrouillage était définitif, et seule une
    /// invalidation par la plateforme effaçait le sceau.
    testWidgets('un sceau posé peut être retiré', (tester) async {
      final magasin = await ouvrirLesReglages(tester, Issue.ouverte);
      await montrerLeSceau(tester);

      await tester.tap(find.byKey(const Key('bouton.retirer.sceau')));
      await tester.pump();
      await tester.pump();

      expect(magasin.oublis, 1);
      await montrerLeSceau(tester);
      expect(find.byKey(const Key('mot.sceau')), findsOneWidget);
      expect(find.text(fr.sceauRetire), findsOneWidget);
    });

    /// On ne se fie pas à `oublier()`, qui avale ses erreurs : on relit. Affirmer un
    /// retrait qu'on n'a pas vérifié serait le réglage menteur, simplement inversé.
    testWidgets('le retrait se relit, il ne se suppose pas', (tester) async {
      final magasin = await ouvrirLesReglages(tester, Issue.ouverte);
      final avant = magasin.lectures;
      await montrerLeSceau(tester);

      await tester.tap(find.byKey(const Key('bouton.retirer.sceau')));
      await tester.pump();
      await tester.pump();

      expect(magasin.lectures, greaterThan(avant),
          reason: 'l\'écran affirme un état qu\'il n\'est pas allé revérifier');
      await montrerLeSceau(tester);
      expect(find.text(fr.sceauAbsent), findsOneWidget);
    });

    /// Un sceau mort se retire aussi : c'est la seule façon de sortir d'un magasin coincé
    /// sans désinstaller l'application.
    testWidgets('un sceau invalidé ou illisible se retire aussi', (tester) async {
      for (final etat in [Issue.invalidee, Issue.echec]) {
        await ouvrirLesReglages(tester, etat);
        await montrerLeSceau(tester);
        expect(find.byKey(const Key('bouton.retirer.sceau')), findsOneWidget,
            reason: '${etat.name} : aucun moyen de repartir de zéro');
      }
    });

    /// Rien à retirer, pas de bouton : un bouton qui ne fait rien promet une action.
    testWidgets('rien à retirer, pas de bouton', (tester) async {
      await ouvrirLesReglages(tester, Issue.absente);
      await montrerLeSceau(tester);
      expect(find.byKey(const Key('bouton.retirer.sceau')), findsNothing);
    });
  });

  /// **Ouvrir les réglages ne doit pas demander un visage.**
  ///
  /// `sceau()` interroge la présence, `rappeler()` la valeur — et seule la seconde
  /// déclenche le matériel. Confondre les deux ferait surgir Face ID chez quelqu'un venu
  /// changer un délai de verrouillage, ce qui apprend à refuser l'invite par réflexe.
  testWidgets('afficher l\'état ne déclenche pas la biométrie', (tester) async {
    final magasin = await ouvrirLesReglages(tester, Issue.ouverte);
    await montrerLeSceau(tester);
    expect(magasin.questions, 0,
        reason: 'les réglages ont demandé la valeur au lieu de la présence');
    expect(magasin.lectures, greaterThan(0),
        reason: 'aucune lecture : l\'état affiché ne vient de nulle part');
  });
}
