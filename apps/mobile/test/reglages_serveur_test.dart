// Changer de serveur, depuis l'endroit qui en affiche un.
//
// ─── Ce que la ligne faisait, et ne faisait pas ───
//
// « Serveur » était un `ListTile` sans `onTap` : il montrait l'adresse comme un réglage
// et ne se touchait pas. Le chemin existait pourtant — Se déconnecter, puis « Utiliser un
// autre compte » sur l'écran de connexion, qui rouvre le champ — mais aucun des deux
// libellés ne parle de serveur, et rien ne menait de l'un à l'autre.
//
// Relevé sur un vrai cas : l'API de `cal.ghostsuite.cloud` vivant sous `/api`, il fallait
// corriger l'adresse. Il a fallu lire le code pour trouver la sortie.
//
// ─── Ce que ce témoin retient ───
//
// Pas l'apparence du dialogue, qui changera. Les deux propriétés qui tiennent le
// parcours : qu'on ne déconnecte **pas** sans accord, et qu'après accord l'écran reparte
// avec l'adresse déjà inscrite — sans quoi le correctif consiste à la retaper de mémoire.

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/ecrans/connexion.dart';
import 'package:ghostcal/ecrans/reglages.dart';
import 'package:ghostcal/services/session.dart';
import 'package:ghostcal/services/verrouillage.dart' as v;

import 'harnais.dart';

/// Compte les déconnexions.
///
/// `Etat.dehors` est l'état **initial** d'une `Session` : affirmer « on n'est pas sorti »
/// en le comparant passerait au vert sur un écran qui déconnecte, comme sur un écran qui
/// ne fait rien. Ce qu'il faut mesurer, c'est l'appel.
class _SessionEspionne extends Session {
  int deconnexions = 0;

  @override
  Future<void> seDeconnecter() async {
    deconnexions++;
    await super.seDeconnecter();
  }
}

Future<void> toucherLaLigneServeur(WidgetTester tester, Session session) async {
  await tester.pumpWidget(appDEpreuve(
    EcranDeReglages(session: session, verrouillage: v.Verrouillage()),
  ));
  await tester.pump();
  // `ensureVisible` et non `scrollUntilVisible` : un `ListView` construit la tuile avant
  // qu'elle entre dans la fenêtre, et le toucher porterait hors écran.
  await tester.ensureVisible(find.byKey(const Key('reglages.serveur')));
  await tester.pump();
  await tester.tap(find.byKey(const Key('reglages.serveur')));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 300));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  _SessionEspionne sessionOuverte() => _SessionEspionne()
    ..serveur = 'cal.ghostsuite.cloud'
    ..email = 'clara@example.com';

  testWidgets('annuler ne déconnecte pas', (tester) async {
    final session = sessionOuverte();
    await toucherLaLigneServeur(tester, session);

    expect(find.text('Changer de serveur'), findsOneWidget,
        reason: 'La ligne doit mener quelque part : c\'est tout le défaut.');

    await tester.tap(find.text('Annuler'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(session.serveur, 'cal.ghostsuite.cloud');
    expect(session.deconnexions, 0,
        reason: 'Refuser le prix ne doit pas le faire payer quand même.');
  });

  testWidgets('accepter déconnecte, et garde l\'adresse à corriger', (tester) async {
    final session = sessionOuverte();
    await toucherLaLigneServeur(tester, session);

    await tester.tap(find.byKey(const Key('reglages.serveur.confirmer')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(session.deconnexions, 1);
    // L'adresse survit à la déconnexion : c'est elle que l'écran de connexion inscrira
    // dans son champ. L'effacer obligerait à la retaper pour y changer quatre caractères.
    expect(session.serveur, 'cal.ghostsuite.cloud');
  });

  testWidgets('l\'écran de connexion rouvre le champ, déjà rempli', (tester) async {
    // Ce que l'utilisateur voit juste après. Sans session enregistrée — la déconnexion
    // retire le jeton de rafraîchissement — l'écran montre le formulaire entier, et non
    // la seule phrase.
    final session = Session()
      ..serveur = 'cal.ghostsuite.cloud'
      ..email = 'clara@example.com';

    await tester.pumpWidget(appDEpreuve(EcranDeConnexion(session: session)));
    await tester.pump();

    final champ = find.byKey(const Key('champ.serveur'));
    expect(champ, findsOneWidget,
        reason: 'Sans ce champ, il n\'y a aucun endroit où corriger l\'adresse.');
    expect(
      tester.widget<TextField>(champ).controller?.text,
      'cal.ghostsuite.cloud',
      reason: 'Pré-rempli : on corrige « cal.ghostsuite.cloud » en '
          '« cal.ghostsuite.cloud/api », on ne le retape pas.',
    );
  });
}
