import 'package:flutter/widgets.dart';

/// The locale dates are formatted in: the screen's, not a hard-coded `fr_FR`.
///
/// Every `DateFormat` used to pass `'fr_FR'`, so an English interface still read
/// "mercredi 14 octobre 2026".
String langueDesDates(BuildContext context) =>
    Localizations.localeOf(context).toLanguageTag();
