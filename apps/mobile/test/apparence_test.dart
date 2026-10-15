// Language and theme chosen in the app, not only inherited from the device.

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/ecrans/reglages.dart';
import 'package:ghostcal/l10n/generated/app_localisations.dart';
import 'package:ghostcal/main.dart';
import 'package:ghostcal/services/apparence.dart';
import 'package:ghostcal/services/session.dart';
import 'package:ghostcal/services/verrouillage.dart' as v;
import 'harnais.dart';

/// Shows the language and brightness the app actually resolved.
class _Sonde extends StatelessWidget {
  const _Sonde();
  @override
  Widget build(BuildContext context) => Text(
        '${L.of(context).langue}|${Theme.of(context).brightness.name}',
        textDirection: TextDirection.ltr,
      );
}

void main() {
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  test('the choice survives a restart', () async {
    final avant = Apparence();
    await avant.choisirLaLangue(ChoixDeLangue.anglais);
    await avant.choisirLeTheme(ChoixDeTheme.sombre);

    final apres = Apparence();
    await apres.amorcer();
    expect(apres.langue, ChoixDeLangue.anglais);
    expect(apres.theme, ChoixDeTheme.sombre);
  });

  test('an unknown stored value falls back to the device', () async {
    FlutterSecureStorage.setMockInitialValues({
      'ghostcal.apparence.langue': 'klingon',
      'ghostcal.apparence.theme': 'neon',
    });
    final apparence = Apparence();
    await apparence.amorcer();
    expect(apparence.langue, ChoixDeLangue.appareil);
    expect(apparence.theme, ChoixDeTheme.appareil);
  });

  testWidgets('the app follows the chosen language and theme', (tester) async {
    final apparence = Apparence();
    await tester.pumpWidget(GhostcalApp(
      session: Session(),
      verrouillage: v.Verrouillage(),
      apparence: apparence,
      accueilDEpreuve: const _Sonde(),
    ));

    await apparence.choisirLaLangue(ChoixDeLangue.anglais);
    await apparence.choisirLeTheme(ChoixDeTheme.sombre);
    await tester.pumpAndSettle();
    expect(find.text('Language|dark'), findsOneWidget);

    await apparence.choisirLaLangue(ChoixDeLangue.francais);
    await apparence.choisirLeTheme(ChoixDeTheme.clair);
    await tester.pumpAndSettle();
    expect(find.text('Langue|light'), findsOneWidget);
  });

  testWidgets('the settings offer both choices', (tester) async {
    await tester.pumpWidget(appDEpreuve(EcranDeReglages(
      session: Session(),
      verrouillage: v.Verrouillage(),
      apparence: Apparence(),
    )));
    await tester.pump();
    expect(find.text('APPARENCE'), findsOneWidget);
    expect(find.byKey(const Key('reglage.langue')), findsOneWidget);
    expect(find.byKey(const Key('reglage.theme')), findsOneWidget);
  });
}
