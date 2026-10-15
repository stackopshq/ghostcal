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
