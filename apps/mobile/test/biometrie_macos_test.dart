// Le contournement d'Android ne doit pas déborder sur macOS.
//
// `biometrie.dart` tient deux chemins, et leur différence n'est pas cosmétique. Android
// passe par un **marqueur** rangé dans le trousseau ordinaire, parce que le greffon y
// présente l'empreinte dès qu'on effleure le magasin scellé — même pour demander s'il est
// vide. Apple ne souffre pas de ce défaut : la question de présence part sous
// `kSecUseAuthenticationUIFail` et répond sans rien présenter.
//
// Appliquer le chemin d'Android à macOS reviendrait à décider de l'état du sceau d'après
// un marqueur posé à côté, pendant que l'entrée gardée, elle, aurait pu disparaître — ce
// qu'Apple fait précisément sous `biometryCurrentSet` quand la biométrie change. Le bouton
// resterait, et il ouvrirait une erreur.
//
// Le garde `_surAndroid` est privé et porte déjà la bonne condition. Ce témoin mesure ce
// qui s'en déduit, et qui se perdrait sans bruit : sur macOS, c'est **le magasin scellé**
// qu'on interroge, jamais le marqueur.

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ghostcal/services/biometrie.dart';

import 'harnais.dart';

void main() {
  late MagasinCompte scelle;
  late MagasinCompte marqueurs;
  late Biometrie biometrie;

  setUp(() {
    debugDefaultTargetPlatformOverride = TargetPlatform.macOS;
    scelle = MagasinCompte();
    marqueurs = MagasinCompte();
    biometrie = Biometrie(stockage: scelle, marqueurs: marqueurs);
  });

  tearDown(() => debugDefaultTargetPlatformOverride = null);

  test('la question de présence interroge le sceau, pas un marqueur', () async {
    expect(await biometrie.sceau(), Issue.absente);
    expect(scelle.appels, 1);
    expect(marqueurs.appels, 0,
        reason: 'le marqueur est une rustine d\'Android et n\'a rien à dire ici');
  });

  test('sceller n\'écrit que la phrase', () async {
    expect(await biometrie.retenir('phrase'), isTrue);
    expect(marqueurs.appels, 0);
    expect(await biometrie.sceau(), Issue.ouverte);
  });

  /// Le chemin qu'Android doit emprunter et que macOS doit éviter : là-bas, une invite de
  /// l'application précède la lecture parce que le magasin reste ouvert pour la vie du
  /// processus. Ici le trousseau redemande le doigt à chaque lecture, et une invite de
  /// plus en ferait deux pour un seul déverrouillage.
  test('oublier efface la phrase elle-même', () async {
    await biometrie.retenir('phrase');
    await biometrie.oublier();
    expect(scelle.valeurs, isEmpty);
    expect(marqueurs.appels, 0);
  });

  test('rappeler rend la phrase scellée', () async {
    await biometrie.retenir('phrase');
    final rappel = await biometrie.rappeler();
    expect(rappel.issue, Issue.ouverte);
    expect(rappel.phrase, 'phrase');
  });
}
