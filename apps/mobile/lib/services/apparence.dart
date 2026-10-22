import 'dart:ui' show PlatformDispatcher;

import 'package:flutter/material.dart';

import '../l10n/generated/app_localisations.dart';
import 'trousseau.dart';

/// The interface language: the device's by default, or one picked in the settings.
enum ChoixDeLangue {
  appareil(null),
  francais(Locale('fr')),
  anglais(Locale('en'));

  const ChoixDeLangue(this.locale);

  /// `null` lets [MaterialApp] follow the device.
  final Locale? locale;

  /// Language names are written in their own language ("Français", "English"), the way
  /// every system picker shows them: someone who cannot read the current interface must
  /// still find their own language.
  String libelle(L l) => switch (this) {
        ChoixDeLangue.appareil => l.langueDeLAppareil,
        ChoixDeLangue.francais => l.langueFrancais,
        ChoixDeLangue.anglais => l.langueAnglais,
      };
}

/// La langue réellement en vigueur, « fr » ou « en », d'après le choix fait dans
/// l'application et, à défaut, la langue de l'appareil.
///
/// Posée hors de la classe pour une raison de mesure : `PlatformDispatcher.instance` est
/// un singleton que le harnais de test n'intercepte pas. Un témoin qui poserait une
/// langue d'appareil factice mesurerait son propre décor pendant que le code lirait le
/// vrai système. On passe donc l'appareil en argument, et c'est le seul moyen d'éprouver
/// le repli.
String codeDeLangueDepuis(ChoixDeLangue choix, Locale appareil) {
  final code = choix.locale?.languageCode ?? appareil.languageCode;
  // Toute autre langue retombe sur le français — le repli documenté de l'application.
  // L'en-tête doit dire la même chose que l'écran : nommer le calendrier dans une langue
  // que l'interface ne parle pas serait pire que de le nommer en français.
  return code == 'en' ? 'en' : 'fr';
}

/// Light, dark, or whatever the device uses.
enum ChoixDeTheme {
  appareil(ThemeMode.system),
  clair(ThemeMode.light),
  sombre(ThemeMode.dark);

  const ChoixDeTheme(this.mode);
  final ThemeMode mode;

  String libelle(L l) => switch (this) {
        ChoixDeTheme.appareil => l.themeDeLAppareil,
        ChoixDeTheme.clair => l.themeClair,
        ChoixDeTheme.sombre => l.themeSombre,
      };
}

/// Language and theme, kept between launches. Same shape as `Verrouillage`.
class Apparence extends ChangeNotifier {
  /// Public for the reminders, which word their notifications without a widget tree.
  static const cleLangue = 'ghostcal.apparence.langue';
  static const _cleTheme = 'ghostcal.apparence.theme';

  ChoixDeLangue _langue = ChoixDeLangue.appareil;
  ChoixDeLangue get langue => _langue;

  ChoixDeTheme _theme = ChoixDeTheme.appareil;
  ChoixDeTheme get theme => _theme;

  /// La langue que le serveur verrait s'il regardait l'écran : « fr » ou « en », jamais
  /// `null`. Elle voyage jusqu'à lui parce qu'il produit **un** texte visible, le nom du
  /// calendrier par défaut, créé à la première lecture de la liste et non à l'inscription.
  String get codeDeLangue =>
      codeDeLangueDepuis(_langue, PlatformDispatcher.instance.locale);

  Future<void> amorcer() async {
    final langue = await Trousseau.lire(cleLangue);
    final theme = await Trousseau.lire(_cleTheme);
    // An unknown value (written by a newer version) falls back to the device's choice.
    _langue = ChoixDeLangue.values.firstWhere((v) => v.name == langue,
        orElse: () => ChoixDeLangue.appareil);
    _theme = ChoixDeTheme.values.firstWhere((v) => v.name == theme,
        orElse: () => ChoixDeTheme.appareil);
    notifyListeners();
  }

  Future<void> choisirLaLangue(ChoixDeLangue valeur) async {
    _langue = valeur;
    notifyListeners();
    await Trousseau.poser(valeur.name, cleLangue);
  }

  Future<void> choisirLeTheme(ChoixDeTheme valeur) async {
    _theme = valeur;
    notifyListeners();
    await Trousseau.poser(valeur.name, _cleTheme);
  }
}
