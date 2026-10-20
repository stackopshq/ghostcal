// Le ré-encodage de la photo n'a lieu que là où le sélecteur ne le fait pas.
//
// Les deux moitiés comptent autant l'une que l'autre, et aucune ne casse quoi que ce soit
// en se trompant : sur macOS, ne pas appeler le canal envoie un HEIC que le serveur
// refuse ; ailleurs, l'appeler ferait un second ré-encodage d'une image qu'`image_picker`
// a déjà réduite — et sur un appareil sans ce canal, une `MissingPluginException` sur le
// parcours normal de la photo de profil.

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/vignette.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const canal = MethodChannel('ch.stackops.ghostcal/vignette');
  late List<MethodCall> appels;

  setUp(() {
    appels = [];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(canal, (appel) async {
      appels.add(appel);
      return Uint8List.fromList([0xFF, 0xD8, 0xFF]); // l'en-tête d'un JPEG
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(canal, null);
  });

  test('sur macOS, l\'image passe par le décodeur du système', () async {
    const vignette = Vignette(plateforme: TargetPlatform.macOS);
    final octets = await vignette.reduire('/tmp/photo.heic');

    expect(octets, isNotNull);
    expect(appels.single.method, 'jpeg');
    expect(appels.single.arguments, {'chemin': '/tmp/photo.heic'});
  });

  for (final plateforme in [TargetPlatform.iOS, TargetPlatform.android]) {
    test('sur $plateforme, le canal n\'est pas sollicité', () async {
      final vignette = Vignette(plateforme: plateforme);
      expect(await vignette.reduire('/tmp/photo.heic'), isNull,
          reason: '`image_picker` y a déjà réduit et ré-encodé');
      expect(appels, isEmpty);
    });
  }

  /// Une panne du décodage doit **remonter**. Rattrapée en rendant `null`, elle serait
  /// indiscernable de « pas sur macOS », et l'appelant téléverserait le HEIC d'origine —
  /// c'est-à-dire exactement ce que le canal existe pour éviter.
  test('une panne native remonte plutôt que de ressembler à « rien à faire »', () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(canal, (_) async {
      throw PlatformException(code: 'decodage', message: 'pas une image');
    });
    const vignette = Vignette(plateforme: TargetPlatform.macOS);
    await expectLater(
      vignette.reduire('/tmp/document.pdf'),
      throwsA(isA<PlatformException>().having((e) => e.code, 'code', 'decodage')),
    );
  });
}
