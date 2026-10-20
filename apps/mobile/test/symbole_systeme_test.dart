// L'icône que l'utilisateur d'iPhone reconnaît, et les trois fois où il ne faut pas la
// laisser manquer.
//
// ─── Ce qui a été mesuré avant d'écrire ce fichier ───
//
// L'écran annonçait Face ID avec `Icons.face` : une tête ronde souriante. Les six
// candidats Material ont été rendus sur simulateur — `face_unlock_outlined`, `_rounded`
// et `_sharp` sont la même tête à quelques pixels près. Material n'a rien qui ressemble
// au cadre à coins tronqués de Face ID, et les HIG interdisent d'en dessiner un sosie.
// D'où le pont vers les SF Symbols, vérifié à l'image : `faceid`, `touchid`,
// `lock.shield` sortent bien le dessin d'Apple.
//
// Ce fichier ne mesure pas le dessin — aucun test ne le peut. Il garde ce qui casserait
// sans bruit : le nom demandé, et le repli.

import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/outils/symbole_systeme.dart';
import 'package:ghostcal/services/biometrie.dart';

import 'harnais.dart';

/// Un PNG valide de 1×1, pour que `Image.memory` ait quelque chose à décoder.
final pngMinuscule = Uint8List.fromList(base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
));

void main() {
  // Avant de toucher au messager : son getter `instance` exige une liaison construite.
  TestWidgetsFlutterBinding.ensureInitialized();
  final messager = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  const canal = MethodChannel('ch.stackops.ghostcal/symboles');

  var appels = <MethodCall>[];

  void repondre(Object? Function(MethodCall) quoi) {
    messager.setMockMethodCallHandler(canal, (appel) async {
      appels.add(appel);
      return quoi(appel);
    });
  }

  setUp(() {
    appels = <MethodCall>[];
    SymboleSysteme.oublierLeCache();
  });

  tearDown(() => messager.setMockMethodCallHandler(canal, null));

  /// Joue [corps] en se faisant passer pour [plateforme], et **remet la variable à zéro
  /// avant la fin du corps du test**.
  ///
  /// Un `tearDown` ne suffit pas : `flutter_test` vérifie que les variables de débogage
  /// de `foundation` sont revenues à leur valeur initiale à la sortie du corps, donc
  /// avant les `tearDown`. Les quatre témoins échouaient sur « The value of a foundation
  /// debug variable was changed by the test », qui ne nomme ni la variable ni le moment.
  Future<void> commeSi(TargetPlatform plateforme, Future<void> Function() corps) async {
    debugDefaultTargetPlatformOverride = plateforme;
    try {
      await corps();
    } finally {
      debugDefaultTargetPlatformOverride = null;
    }
  }

  // GhostPass iOS affiche ces trois noms-là, dans `Biometrics.icon`. Deux produits de la
  // même suite qui annoncent le même geste doivent montrer le même dessin ; si l'un des
  // deux dérive, c'est ici qu'on l'apprend.
  test('les trois noms sont ceux de GhostPass', () {
    expect(Empreinte.visage.symbole, 'faceid');
    expect(Empreinte.doigt.symbole, 'touchid');
    expect(Empreinte.autre.symbole, 'lock.shield');
  });

  testWidgets('hors iOS, l\'icône Material, et aucun appel au canal', (tester) async {
    await commeSi(TargetPlatform.android, () async {
      repondre((_) => pngMinuscule);

      await tester.pumpWidget(appDEpreuve(const SymboleSysteme(
        nom: 'faceid',
        materiel: Icons.face,
      )));
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.face), findsOneWidget);
      expect(appels, isEmpty, reason: 'Android n\'a pas de SF Symbols à demander.');
    });
  });

  testWidgets('sur iOS, le symbole remplace l\'icône', (tester) async {
    await commeSi(TargetPlatform.iOS, () async {
      repondre((_) => pngMinuscule);

      await tester.pumpWidget(appDEpreuve(const SymboleSysteme(
        nom: 'faceid',
        materiel: Icons.face,
      )));
      await tester.pumpAndSettle();

      expect(appels.single.method, 'rendre');
      expect((appels.single.arguments as Map)['nom'], 'faceid');
      expect(find.byType(Image), findsOneWidget);
      expect(find.byIcon(Icons.face), findsNothing);
    });
  });

  // Le cas qui laisserait un trou à l'écran : une version d'iOS qui ne connaît pas le
  // nom demandé rend `nil`, et non une erreur. Sans repli, l'écran de déverrouillage
  // afficherait un vide à l'endroit exact où il demande qu'on lui fasse confiance.
  testWidgets('un symbole inconnu retombe sur Material', (tester) async {
    await commeSi(TargetPlatform.iOS, () async {
      repondre((_) => null);

      await tester.pumpWidget(appDEpreuve(const SymboleSysteme(
        nom: 'symbole.qui.nexiste.pas',
        materiel: Icons.face,
      )));
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.face), findsOneWidget);
    });
  });

  testWidgets('un canal absent retombe sur Material', (tester) async {
    await commeSi(TargetPlatform.iOS, () async {
      // Pas de gestionnaire : `MissingPluginException`. C'est ce que rendrait une
      // version de l'application dont le pont natif n'a pas été embarqué.
      await tester.pumpWidget(appDEpreuve(const SymboleSysteme(
        nom: 'faceid',
        materiel: Icons.fingerprint,
      )));
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.fingerprint), findsOneWidget);
    });
  });
}
