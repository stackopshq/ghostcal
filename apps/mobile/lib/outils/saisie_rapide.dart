/// Fantastical-style quick entry, French and English: "Déjeuner avec Camille demain
/// 12h30 au Café du Marché", "Call with Sam friday 2pm for 1h". Pure and local: what is
/// typed never leaves the device before it is sealed (the web does the same with
/// chrono-node in `frontend/src/lib/quickAdd.ts`).
library;

class ResultatDeSaisie {
  const ResultatDeSaisie({
    required this.titre,
    this.debut,
    this.fin,
    this.journeeEntiere = false,
    this.lieu = '',
  });

  final String titre;

  /// Start; `null` when no date or time was recognised.
  final DateTime? debut;
  final DateTime? fin;

  /// A date without a time.
  final bool journeeEntiere;
  final String lieu;
}

const _joursFr = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'];
const _joursEn = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const _moisFr = [
  'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
  'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
];
const _moisEn = [
  'january', 'february', 'march', 'april', 'may', 'june',
  'july', 'august', 'september', 'october', 'november', 'december',
];

/// The month (1–12) a word names, French or English, full or abbreviated (≥ 3 letters).
int? _mois(String mot) {
  final m = mot.toLowerCase().replaceAll('.', '');
  if (m.length < 3) return null;
  for (var i = 0; i < 12; i++) {
    final fr = _moisFr[i].replaceAll('é', 'e').replaceAll('û', 'u');
    final sansAccent = m.replaceAll('é', 'e').replaceAll('û', 'u');
    if (_moisFr[i].startsWith(m) || fr.startsWith(sansAccent) || _moisEn[i].startsWith(m)) {
      return i + 1;
    }
  }
  return null;
}

ResultatDeSaisie analyserLaSaisie(String saisie, {DateTime? maintenant}) {
  final ref = maintenant ?? DateTime.now();
  var reste = ' ${saisie.trim()} ';
  DateTime? jour;
  int? heure, minute, heureFin, minuteFin;
  Duration? duree;

  String retirer(RegExpMatch m) => '${reste.substring(0, m.start)} ${reste.substring(m.end)}';

  // ── Time range: "14h-16h", "14:00–15:30", "2pm-4pm", "de 14h à 16h", "from 2 to 4pm"
  final plage = RegExp(
    r"\s(?:de |from )?(\d{1,2})(?:[h:](\d{2})?)?\s*(am|pm)?\s*(?:-|–|à|to)\s*(\d{1,2})(?:[h:](\d{2})?)?\s*(am|pm)?(?=\s)",
    caseSensitive: false,
  ).firstMatch(reste);
  if (plage != null && (plage.group(0)!.contains(RegExp(r'[h:]|am|pm', caseSensitive: false)))) {
    final pm2 = plage.group(6)?.toLowerCase();
    final pm1 = plage.group(3)?.toLowerCase() ?? pm2;
    heure = _h24(int.parse(plage.group(1)!), pm1);
    minute = int.tryParse(plage.group(2) ?? '') ?? 0;
    heureFin = _h24(int.parse(plage.group(4)!), pm2);
    minuteFin = int.tryParse(plage.group(5) ?? '') ?? 0;
    reste = retirer(plage);
  }

  // ── Duration: "pendant 2h", "for 1h30", "for 45 min", "1h", "30 min"
  final dureeM = RegExp(
    r"\s(?:pendant |for |durant )?(\d{1,2})\s?(?:h|hours?|heures?)\s?(\d{2})?(?:\s?min)?(?=\s)|\s(?:pendant |for |durant )?(\d{1,3})\s?(?:min|minutes?|mn)(?=\s)",
    caseSensitive: false,
  );
  // A bare "14h" is a time, not a duration: only take an hour count when it is
  // introduced ("pendant", "for") or when a start time is already known.
  for (final m in dureeM.allMatches(reste)) {
    final texte = m.group(0)!.toLowerCase();
    final introduit = texte.contains('pendant') || texte.contains('for') || texte.contains('durant');
    if (m.group(3) != null) {
      duree = Duration(minutes: int.parse(m.group(3)!));
      reste = retirer(m);
      break;
    }
    if (introduit) {
      duree = Duration(hours: int.parse(m.group(1)!), minutes: int.tryParse(m.group(2) ?? '') ?? 0);
      reste = retirer(m);
      break;
    }
  }

  // ── Time: "à 14h30", "14h", "14:30", "at 2pm", "2:30pm", "midi", "noon"
  if (heure == null) {
    final midi = RegExp(r"\s(?:à |at )?(midi|noon)(?=\s)", caseSensitive: false).firstMatch(reste);
    if (midi != null) {
      heure = 12;
      minute = 0;
      reste = retirer(midi);
    } else {
      final h = RegExp(
        r"\s(?:à |a |at |@ ?)?(\d{1,2})(?:(?:h|:)(\d{2})?\s*(am|pm)?|\s?(am|pm))(?=\s)",
        caseSensitive: false,
      ).firstMatch(reste);
      if (h != null) {
        final suffixe = (h.group(3) ?? h.group(4))?.toLowerCase();
        final valeur = int.parse(h.group(1)!);
        if (valeur <= 24) {
          heure = _h24(valeur, suffixe);
          minute = int.tryParse(h.group(2) ?? '') ?? 0;
          reste = retirer(h);
        }
      }
    }
  }

  // ── Day
  final relatif = RegExp(
    r"\s(aujourd'hui|aujourdhui|today|ce soir|tonight|après-demain|apres-demain|day after tomorrow|demain|tomorrow)(?=\s)",
    caseSensitive: false,
  ).firstMatch(reste);
  if (relatif != null) {
    final mot = relatif.group(1)!.toLowerCase();
    final decalage = mot.contains('après') || mot.contains('apres') || mot.contains('after')
        ? 2
        : mot.contains('demain') || mot.contains('tomorrow')
            ? 1
            : 0;
    jour = DateTime(ref.year, ref.month, ref.day + decalage);
    if ((mot == 'ce soir' || mot == 'tonight') && heure == null) {
      heure = 19;
      minute = 0;
    }
    reste = retirer(relatif);
  }
  if (jour == null) {
    final semaine = RegExp(
      r"\s(?:(?:next|prochain|ce|this)\s)?(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?:\s(?:prochain|next))?(?=\s)",
      caseSensitive: false,
    ).firstMatch(reste);
    if (semaine != null) {
      final mot = semaine.group(1)!.toLowerCase();
      var index = _joursFr.indexOf(mot);
      if (index < 0) index = _joursEn.indexOf(mot);
      final cible = index + 1; // DateTime.monday == 1
      var ecart = (cible - ref.weekday) % 7;
      if (ecart == 0) ecart = 7; // "lundi" on a Monday means next Monday
      jour = DateTime(ref.year, ref.month, ref.day + ecart);
      reste = retirer(semaine);
    }
  }
  if (jour == null) {
    // "15/10", "15.10", "15/10/2027"
    final numerique =
        RegExp(r"\s(?:le |on )?(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?(?=\s)").firstMatch(reste);
    if (numerique != null) {
      jour = _date(ref, int.parse(numerique.group(1)!), int.parse(numerique.group(2)!),
          numerique.group(3));
      if (jour != null) reste = retirer(numerique);
    }
  }
  if (jour == null) {
    // "15 octobre", "le 3 mars 2027", "Oct 15", "october 15th"
    final jourMois = RegExp(r"\s(?:le |on )?(\d{1,2})(?:er|st|nd|rd|th)?\s([a-zéû.]{3,})(?:\s(\d{4}))?(?=\s)",
            caseSensitive: false)
        .firstMatch(reste);
    final moisJour = RegExp(r"\s(?:on )?([a-z.]{3,})\s(\d{1,2})(?:st|nd|rd|th)?(?:,?\s(\d{4}))?(?=\s)",
            caseSensitive: false)
        .firstMatch(reste);
    if (jourMois != null && _mois(jourMois.group(2)!) != null) {
      jour = _date(ref, int.parse(jourMois.group(1)!), _mois(jourMois.group(2)!)!, jourMois.group(3));
      if (jour != null) reste = retirer(jourMois);
    } else if (moisJour != null && _mois(moisJour.group(1)!) != null) {
      jour = _date(ref, int.parse(moisJour.group(2)!), _mois(moisJour.group(1)!)!, moisJour.group(3));
      if (jour != null) reste = retirer(moisJour);
    }
  }

  // ── Location: what follows "au", "à la", "chez", "at", "@" (capitalised or quoted)
  var lieu = '';
  final lieuM = RegExp(
    r"\s(?:au|à la|à l'|aux|chez|at the|at|@|à)\s+([A-ZÀ-Ý0-9][^,;]*?)\s*$",
  ).firstMatch('${reste.trimRight()} ');
  if (lieuM != null) {
    lieu = lieuM.group(1)!.trim();
    reste = reste.substring(0, lieuM.start);
  }

  final titre = reste
      .replaceAll(RegExp(r'\s+'), ' ')
      .replaceAll(RegExp(r'\s(?:le|on|at|à|a|de|from|pendant|for)\s*$', caseSensitive: false), '')
      .trim();

  if (jour == null && heure == null) {
    return ResultatDeSaisie(titre: titre, lieu: lieu);
  }
  var base = jour ?? DateTime(ref.year, ref.month, ref.day);
  if (heure == null) {
    return ResultatDeSaisie(
      titre: titre,
      debut: base,
      fin: DateTime(base.year, base.month, base.day + 1),
      journeeEntiere: true,
      lieu: lieu,
    );
  }
  var debut = DateTime(base.year, base.month, base.day, heure, minute ?? 0);
  // A time alone that is already past today means tomorrow, as in Fantastical.
  if (jour == null && debut.isBefore(ref)) {
    debut = debut.add(const Duration(days: 1));
  }
  final fin = heureFin != null
      ? DateTime(debut.year, debut.month, debut.day, heureFin, minuteFin ?? 0)
      : debut.add(duree ?? const Duration(hours: 1));
  return ResultatDeSaisie(
    titre: titre,
    debut: debut,
    fin: fin.isAfter(debut) ? fin : fin.add(const Duration(days: 1)),
    lieu: lieu,
  );
}

int _h24(int h, String? suffixe) {
  if (suffixe == 'pm' && h < 12) return h + 12;
  if (suffixe == 'am' && h == 12) return 0;
  return h;
}

/// A day/month (and optional year); the next occurrence when the year is omitted.
DateTime? _date(DateTime ref, int jour, int mois, String? annee) {
  if (mois < 1 || mois > 12 || jour < 1 || jour > 31) return null;
  var a = annee == null ? ref.year : int.parse(annee);
  if (a < 100) a += 2000;
  var d = DateTime(a, mois, jour);
  if (d.month != mois) return null; // 31 February
  if (annee == null && d.isBefore(DateTime(ref.year, ref.month, ref.day))) {
    d = DateTime(a + 1, mois, jour);
  }
  return d;
}
