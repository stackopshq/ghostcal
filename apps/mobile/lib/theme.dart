import 'dart:ui';

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

  /// La teinte de marque du halo. Fixe : elle ne s'adapte pas au thème, c'est une
  /// source de lumière, pas une surface.
  static const neon = Color(0xFF2E7DFF);
  static const surAccent = Colors.white;

  /// Le même halo, pour du **texte**.
  ///
  /// Un `BoxShadow` suit la boîte : posé derrière des lettres, il peint un rectangle
  /// coloré au lieu de les faire rayonner. Seules les ombres du style de texte suivent
  /// la forme des glyphes, comme le fait `.shadow` en SwiftUI.
  List<Shadow> haloDeTexte(double force) {
    final echelle = sombre ? force : force * 0.45;
    if (echelle <= 0) return const [];
    return [
      Shadow(color: neon.withValues(alpha: 0.60 * echelle), blurRadius: 8 * echelle),
      Shadow(color: neon.withValues(alpha: 0.35 * echelle), blurRadius: 20 * echelle),
    ];
  }

  /// Le halo néon de la suite : **deux** rayonnements superposés, l'un serré et vif,
  /// l'autre large et diffus.
  ///
  /// Transposition du `--brand-glow` partagé. Les deux comptent : un seul halo fait une
  /// tache molle, tandis que la superposition d'un noyau net et d'une aura étalée donne
  /// l'impression d'une source de lumière. Le rayon est réduit en thème clair, où un néon
  /// sur fond blanc devient une bavure.
  List<BoxShadow> halo(double force) {
    final echelle = sombre ? force : force * 0.45;
    if (echelle <= 0) return const [];
    return [
      BoxShadow(color: neon.withValues(alpha: 0.60 * echelle), blurRadius: 8 * echelle),
      BoxShadow(color: neon.withValues(alpha: 0.35 * echelle), blurRadius: 20 * echelle),
    ];
  }
}

/// Mesures partagées. Les mêmes que sur le web et sur iOS : contrôles à 12, cartes à 16.
class Mesures {
  static const rayon = 12.0;
  static const rayonCarte = 16.0;
  static const ecart = 12.0;
  static const marge = 16.0;
  static const margeCarte = 24.0;
}

/// Le fond de l'application : nuit profonde et halo diffusé depuis le haut — la lueur du
/// fantôme, qui donne sa profondeur à l'ensemble sans rien coûter en lisibilité.
///
/// En thème clair, le dégradé disparaît : quatre nuances de blanc ne se distinguent pas,
/// et le halo y reste, mais faible.
class FondGhost extends StatelessWidget {
  const FondGhost({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    return Stack(
      children: [
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: gc.sombre
                  ? const LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        Color(0xFF080D18),
                        Color(0xFF0A1220),
                        Color(0xFF080F1A),
                        Color(0xFF090A10),
                      ],
                    )
                  : null,
              color: gc.sombre ? null : gc.base,
            ),
          ),
        ),
        Positioned(
          top: -140,
          left: 0,
          right: 0,
          height: 620,
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  center: Alignment.topCenter,
                  radius: 0.9,
                  colors: [
                    Gc.neon.withValues(alpha: gc.sombre ? 0.26 : 0.12),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),
        ),
        child,
      ],
    );
  }
}

/// Carte de verre fumé : surface translucide, filet clair, et le flou qui la rend vitreuse.
///
/// Le `BackdropFilter` est ce qui distingue une carte de verre d'un rectangle gris : sans
/// lui, la translucidité ne montre rien puisque rien n'est flouté derrière.
class CarteDeVerre extends StatelessWidget {
  const CarteDeVerre({super.key, required this.child, this.marge = Mesures.margeCarte});

  final Widget child;
  final double marge;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    return ClipRRect(
      borderRadius: BorderRadius.circular(Mesures.rayonCarte),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
        child: Container(
          padding: EdgeInsets.all(marge),
          decoration: BoxDecoration(
            color: gc.surface.withValues(alpha: 0.65),
            borderRadius: BorderRadius.circular(Mesures.rayonCarte),
            border: Border.all(color: gc.bordure),
          ),
          child: child,
        ),
      ),
    );
  }
}

/// Action principale : un bloc d'accent plein, pleine largeur, qui rayonne.
class BoutonPrincipal extends StatelessWidget {
  const BoutonPrincipal({super.key, required this.child, this.onPressed});

  final Widget child;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final actif = onPressed != null;
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(Mesures.rayon),
        // Seule l'action disponible rayonne. Faire luire un bouton inerte appellerait
        // l'œil vers ce sur quoi on ne peut pas appuyer.
        boxShadow: gc.halo(actif ? 0.85 : 0),
      ),
      child: Material(
        color: gc.accent.withValues(alpha: actif ? 1 : 0.35),
        borderRadius: BorderRadius.circular(Mesures.rayon),
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(Mesures.rayon),
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(vertical: 15),
            alignment: Alignment.center,
            child: DefaultTextStyle.merge(
              style: const TextStyle(
                color: Gc.surAccent,
                fontWeight: FontWeight.w600,
                fontSize: 16,
              ),
              child: child,
            ),
          ),
        ),
      ),
    );
  }
}

ThemeData themeGhostcal(Brightness luminosite) {
  final gc = Gc._(luminosite == Brightness.dark);
  return ThemeData(
    useMaterial3: true,
    brightness: luminosite,
    colorScheme: ColorScheme.fromSeed(
      seedColor: Gc.neon,
      brightness: luminosite,
      surface: gc.surface,
      // Sans cette ligne, `ColorScheme.fromSeed` fabrique un bleu marine terne à partir
      // de la graine et le pose sur tous les boutons : l'accent de la charte n'apparaît
      // nulle part, alors qu'il est la seule couleur vive de l'interface.
      primary: gc.accent,
      onPrimary: Gc.surAccent,
    ),
    // Le fond est peint par `FondGhost`, qui porte le dégradé et le halo. Un Scaffold
    // opaque par-dessus les masquerait tous les deux.
    scaffoldBackgroundColor: Colors.transparent,
    appBarTheme: AppBarTheme(
      backgroundColor: Colors.transparent,
      surfaceTintColor: Colors.transparent,
      foregroundColor: gc.encre,
      elevation: 0,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: gc.surface2,
      hintStyle: TextStyle(color: gc.estompe.withValues(alpha: 0.7)),
      contentPadding:
          const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(Mesures.rayon),
        borderSide: BorderSide(color: gc.bordure),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(Mesures.rayon),
        borderSide: BorderSide(color: gc.bordure),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(Mesures.rayon),
        borderSide: BorderSide(color: gc.accentTexte, width: 1.5),
      ),
    ),
  );
}
