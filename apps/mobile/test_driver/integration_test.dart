import 'package:integration_test/integration_test_driver.dart';

/// Le côté **hôte** de `flutter drive`.
///
/// Il ne fait rien de particulier : la prise de vue n'est pas faite par Flutter mais par
/// `xcrun simctl io … screenshot`, depuis `tools/ios/captures-appstore.sh`.
///
/// Pourquoi ne pas employer `binding.takeScreenshot()` : il rend la **surface Flutter**,
/// dont les dimensions suivent le rendu logique et non la dalle. App Store Connect exige
/// des dimensions exactes — 1320 × 2868 pour un 6,9 pouces — et refuse une image
/// redimensionnée après coup. `simctl` rend ce que l'appareil affiche, barre d'état
/// comprise, à la taille native. C'est la seule voie qui produise un fichier acceptable.
Future<void> main() => integrationDriver();
