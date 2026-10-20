// The Android presence check must never open the sealed store.
//
// Measured on a Redmi Note 9S (2026-10-14): `flutter_secure_storage` 11 initialises a
// namespace on its first call, whatever it is, and under `enforceBiometrics` that shows
// the prompt. A presence check that touches the sealed store therefore prompts on
// launch and on opening the settings.

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/biometrie.dart';

import 'harnais.dart';

void main() {
  late MagasinCompte scelle;
  late MagasinCompte marqueurs;
  late Biometrie biometrie;

  setUp(() {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    scelle = MagasinCompte();
    marqueurs = MagasinCompte();
    biometrie = Biometrie(stockage: scelle, marqueurs: marqueurs);
  });

  tearDown(() => debugDefaultTargetPlatformOverride = null);

  test('nothing sealed: the presence check answers without opening the sealed store',
      () async {
    expect(await biometrie.sceau(), Issue.absente);
    expect(scelle.appels, 0);
  });

  test('sealing sets the marker, and the presence check reads only the marker', () async {
    expect(await biometrie.retenir('phrase'), isTrue);
    final avant = scelle.appels;

    expect(await biometrie.sceau(), Issue.ouverte);
    expect(scelle.appels, avant, reason: 'the presence check would show the prompt');
  });

  test('forgetting removes the marker', () async {
    await biometrie.retenir('phrase');
    await biometrie.oublier();
    expect(await biometrie.sceau(), Issue.absente);
  });

  test('a marker whose phrase is gone reads as absent, not as open', () async {
    await biometrie.retenir('phrase');
    scelle.valeurs.clear(); // what `resetOnError` does to an invalidated store
    // The store is already open in this process, so the app-level prompt runs first;
    // under `flutter test` local_auth has no platform side and is not reached here.
    expect((await Biometrie(stockage: scelle).rappeler()).issue, Issue.absente);
  });
}
