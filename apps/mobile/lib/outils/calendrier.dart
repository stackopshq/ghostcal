/// Date arithmetic for the agenda views. Pure, local time, midnight-based.
library;

/// Midnight of [d]'s day.
DateTime minuit(DateTime d) => DateTime(d.year, d.month, d.day);

/// [d] shifted by [jours] calendar days. Built from the date parts, not by adding
/// 24-hour durations, so a DST change cannot land on 23:00 or 01:00.
DateTime plusJours(DateTime d, int jours) =>
    DateTime(d.year, d.month, d.day + jours);

bool memeJour(DateTime a, DateTime b) =>
    a.year == b.year && a.month == b.month && a.day == b.day;

/// The first day of [d]'s week, given the locale's first weekday as
/// `MaterialLocalizations.firstDayOfWeekIndex` gives it (0 = Sunday, 1 = Monday…).
DateTime debutDeSemaine(DateTime d, int premierJour) {
  final indexDuJour =
      d.weekday % 7; // DateTime: Monday = 1 … Sunday = 7 → Sunday = 0
  final recul = (indexDuJour - premierJour) % 7;
  return plusJours(minuit(d), -recul);
}

/// The 42 days (6 weeks) a month grid shows for [d]'s month, starting on the locale's
/// first weekday. Always six rows, so the grid does not jump in height between months.
List<DateTime> joursDeLaGrilleDuMois(DateTime d, int premierJour) {
  final debut = debutDeSemaine(DateTime(d.year, d.month), premierJour);
  return [for (var i = 0; i < 42; i++) plusJours(debut, i)];
}

/// Les douze premiers jours de chaque mois de l'année de [d], pour la vue Année.
List<DateTime> moisDeLAnnee(DateTime d) => [
  for (var m = 1; m <= 12; m++) DateTime(d.year, m),
];

/// [d] déplacé de [annees] années. Le 29 février d'une année bissextile tombe sur le
/// 28 d'une année qui ne l'est pas, plutôt que de déborder sur mars.
DateTime plusAnnees(DateTime d, int annees) {
  final dernier = DateTime(d.year + annees, d.month + 1, 0).day;
  return DateTime(d.year + annees, d.month, d.day > dernier ? dernier : d.day);
}

/// [d] moved by [mois] months, the day clamped to the target month's length
/// (31 January + 1 month = 28 or 29 February, not 3 March).
DateTime plusMois(DateTime d, int mois) {
  final cible = DateTime(d.year, d.month + mois);
  final dernier = DateTime(cible.year, cible.month + 1, 0).day;
  return DateTime(cible.year, cible.month, d.day > dernier ? dernier : d.day);
}
