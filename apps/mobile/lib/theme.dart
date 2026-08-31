import 'package:flutter/material.dart';

/// La palette de GhostCal, reprise valeur par valeur de `Theme.swift`.
///
/// Les mêmes teintes que le client natif et que le web : une application qui a sa propre
/// idée des couleurs se remarque immédiatement quand on passe de l'une à l'autre.
///
/// Chaque couleur existe en deux versions parce que le thème sombre n'est pas le clair
/// assombri — le texte estompé y devient plus bleu, pas seulement plus pâle.
class Gc {
  const Gc._(this.sombre);

  final bool sombre;

  factory Gc.of(BuildContext context) =>
      Gc._(Theme.of(context).brightness == Brightness.dark);

  Color _c(int fonce, int clair) => Color(0xFF000000 | (sombre ? fonce : clair));

  Color get base => _c(0x21222C, 0xF5F8FC);
  Color get surface => _c(0x282A36, 0xFFFFFF);
  Color get surface2 => _c(0x323445, 0xEEF3F9);
  Color get encre => _c(0xF8F8F2, 0x0F1B2D);
  Color get estompe => _c(0x8B9CC8, 0x5B6B82);
  Color get accent => _c(0x00F0FF, 0x0E8FA8);

  /// L'accent lisible **en texte**. Le turquoise du thème sombre passe sur un aplat, pas
  /// derrière des lettres : sur fond clair il tombe sous le rapport de contraste.
  Color get accentTexte => _c(0x7FB2FF, 0x1A4FCC);

  Color get bordure =>
      sombre ? Colors.white.withValues(alpha: 0.08) : const Color(0x1A0F172A);
  Color get bordureFranche =>
      sombre ? Colors.white.withValues(alpha: 0.16) : const Color(0x290F172A);

  Color get danger => _c(0xFF5555, 0xD11F45);
  Color get succes => _c(0x50FA7B, 0x15803D);
}

ThemeData themeGhostcal(Brightness luminosite) {
  final gc = Gc._(luminosite == Brightness.dark);
  return ThemeData(
    useMaterial3: true,
    brightness: luminosite,
    scaffoldBackgroundColor: gc.base,
    colorScheme: ColorScheme.fromSeed(
      seedColor: const Color(0xFF2E7DFF),
      brightness: luminosite,
      surface: gc.surface,
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: gc.base,
      foregroundColor: gc.encre,
      elevation: 0,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: gc.surface2,
      hintStyle: TextStyle(color: gc.estompe.withValues(alpha: 0.7)),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: gc.bordure),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: gc.bordure),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: gc.accentTexte, width: 1.5),
      ),
    ),
  );
}
