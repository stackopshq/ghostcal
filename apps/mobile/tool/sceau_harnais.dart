// Le harnais qui éprouve vraiment le sceau, parce qu'il **redémarre le processus**.
//
// ─── Pourquoi il existe ───
//
// `integration_test/biometrie_scelle_test.dart` scelle, relit, attend un nouvel
// enrôlement, relit encore — le tout dans une seule exécution. Mesuré : la seconde
// lecture ne déclenche **aucune** invite biométrique. Une seule authentification crypto
// apparaît dans le journal du système pour tout le test, celle de la première lecture.
// La seconde est donc servie sans passer par le KeyStore — vraisemblablement par le
// chiffreur déjà initialisé en mémoire.
//
// Ce témoin-là ne peut donc rien dire de la garantie : il mesure un cache. Et il penchait
// du côté rassurant, ce qui est la pire façon de se tromper.
//
// ─── Ce que ce harnais fait de différent ───
//
// Il s'exécute en deux **lancements séparés** de la même installation, donc deux
// processus, sans rien en mémoire de commun :
//
//   1. rien de scellé  → il scelle, relit, et annonce `HARNAIS: scelle=...` ;
//   2. (l'hôte enrôle une nouvelle empreinte) ;
//   3. déjà scellé     → il relit, et annonce `HARNAIS: relecture=...`.
//
// La phase se déduit de l'état du magasin : pas de marqueur à tenir à jour, donc rien qui
// puisse mentir sur la phase où l'on se trouve.
//
// Il ne s'installe pas par `flutter test`, qui désinstalle l'application à la fin de
// chaque exécution et emporterait le magasin avec elle — constaté, `pm list packages` ne
// trouvait plus le paquet entre les deux phases.
//
//   flutter build apk --debug --target=tool/sceau_harnais.dart
//   adb install -r build/app/outputs/flutter-apk/app-debug.apk
//   adb shell am start -n ch.stackops.ghostcal/.MainActivity   # phase 1
//   …enrôler…
//   adb shell am start -n ch.stackops.ghostcal/.MainActivity   # phase 2
//
// La sortie se lit dans `adb logcat`.

import 'package:flutter/material.dart';
import 'package:ghostcal/services/biometrie.dart';

const temoin = 'phrase-temoin-du-harnais-2026';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const _Ecran());

  final biometrie = Biometrie();

  // L'état du magasin **est** la phase : rien à tenir à jour, donc rien qui puisse
  // mentir sur la phase où l'on se trouve.
  final etat = await biometrie.sceau();
  debugPrint('HARNAIS: sceau=$etat');

  if (etat != Issue.ouverte) {
    await biometrie.retenir(temoin);
    final rappel = await biometrie.rappeler();
    debugPrint('HARNAIS: scelle=${rappel.issue}'
        ' conforme=${rappel.phrase == temoin}');
    return;
  }

  // La lecture qui compte : nouveau processus, rien en mémoire, après enrôlement.
  final rappel = await biometrie.rappeler();
  debugPrint('HARNAIS: relecture=${rappel.issue}'
      ' conforme=${rappel.phrase == temoin}'
      ' detail=${rappel.detail}');
}

class _Ecran extends StatelessWidget {
  const _Ecran();

  @override
  Widget build(BuildContext context) => const MaterialApp(
        home: Scaffold(body: Center(child: Text('harnais du sceau'))),
      );
}
