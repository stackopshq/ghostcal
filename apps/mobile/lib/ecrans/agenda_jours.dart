import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../l10n/generated/app_localisations.dart';
import '../outils/calendrier.dart';
import '../outils/dates.dart';
import '../services/agenda.dart';
import '../services/taches.dart';
import '../theme.dart';
import 'agenda_vues.dart';

/// The agenda read as a list of days, Fantastical-style: one section per day — "TODAY",
/// "TOMORROW", then the weekday — with the day's tasks first and its events after.
///
/// Used under the compact month grid and as the list view. Empty days keep their header:
/// a gap in the dates reads as a missing day, not as a free one.
class ListeParJour extends StatelessWidget {
  const ListeParJour({
    super.key,
    required this.debut,
    required this.jours,
    required this.lignes,
    required this.taches,
    required this.couleurDe,
    required this.surLigne,
    required this.surTache,
    this.maintenant,
    this.controleur,
    this.basDePage = 88,
  });

  /// The first day shown.
  final DateTime debut;

  /// How many days are shown from [debut].
  final int jours;
  final List<LigneDAgenda> lignes;

  /// Every task the user has; the list picks those due on the days it shows.
  final List<Tache> taches;
  final CouleurDe couleurDe;
  final ValueChanged<LigneDAgenda> surLigne;

  /// Ticking a task's box.
  final ValueChanged<Tache> surTache;

  /// Injected by tests; the clock otherwise.
  final DateTime? maintenant;
  final ScrollController? controleur;

  /// Room left under the last day for the floating button.
  final double basDePage;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final l = L.of(context);
    final instant = maintenant ?? DateTime.now();
    final aujourdhui = minuit(instant);
    final sections = <Widget>[];
    var quelqueChose = false;
    for (var i = 0; i < jours; i++) {
      final jour = plusJours(debut, i);
      final evenements = lignes.where((x) => couvre(x, jour)).toList()
        ..sort(Agenda.comparerLesLignes);
      final duJour = tachesDuJour(taches, jour, maintenant: instant);
      quelqueChose |= evenements.isNotEmpty || duJour.isNotEmpty;
      sections.add(
        _Section(
          key: Key('jour.${jour.month}.${jour.day}'),
          jour: jour,
          aujourdhui: aujourdhui,
          premier: i == 0,
          evenements: evenements,
          taches: duJour,
          couleurDe: couleurDe,
          surLigne: surLigne,
          surTache: surTache,
          maintenant: instant,
        ),
      );
    }
    if (!quelqueChose) {
      sections.insert(
        sections.isEmpty ? 0 : 1,
        Padding(
          padding: const EdgeInsets.fromLTRB(
            Mesures.marge,
            8,
            Mesures.marge,
            8,
          ),
          child: Text(l.rienSurLaPeriode, style: TextStyle(color: gc.estompe)),
        ),
      );
    }
    return ListView(
      controller: controleur,
      padding: EdgeInsets.only(bottom: basDePage),
      children: sections,
    );
  }
}

/// The tasks a day's section lists: those due that day, not done. Today also gathers
/// every overdue task, so a late one stays in sight instead of sinking into the past.
List<Tache> tachesDuJour(
  List<Tache> taches,
  DateTime jour, {
  required DateTime maintenant,
}) {
  final aujourdhui = memeJour(jour, maintenant);
  final retenues = taches.where((t) {
    final echeance = t.echeance;
    if (t.faite || echeance == null) return false;
    if (memeJour(echeance, jour)) return true;
    return aujourdhui && echeance.isBefore(minuit(maintenant));
  }).toList();
  return Taches.ordonner(retenues);
}

class _Section extends StatelessWidget {
  const _Section({
    super.key,
    required this.jour,
    required this.aujourdhui,
    required this.premier,
    required this.evenements,
    required this.taches,
    required this.couleurDe,
    required this.surLigne,
    required this.surTache,
    required this.maintenant,
  });

  final DateTime jour;
  final DateTime aujourdhui;
  final bool premier;
  final List<LigneDAgenda> evenements;
  final List<Tache> taches;
  final CouleurDe couleurDe;
  final ValueChanged<LigneDAgenda> surLigne;
  final ValueChanged<Tache> surTache;
  final DateTime maintenant;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final vide = evenements.isEmpty && taches.isEmpty;
    return Container(
      decoration: BoxDecoration(
        border: premier
            ? null
            : Border(top: BorderSide(color: gc.bordureFranche)),
      ),
      padding: EdgeInsets.only(top: 14, bottom: vide ? 10 : 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _EnTeteDeJour(jour: jour, aujourdhui: aujourdhui),
          if (!vide) const SizedBox(height: 4),
          for (final t in taches)
            _LigneDeTache(
              tache: t,
              jour: jour,
              surTache: surTache,
              maintenant: maintenant,
            ),
          for (final e in evenements)
            _LigneDEvenement(
              ligne: e,
              jour: jour,
              couleur: couleurDe(e),
              surLigne: surLigne,
            ),
        ],
      ),
    );
  }
}

/// "TODAY 20/10/2026": the relative name in capitals, the date beside it in the muted
/// colour. Today's name takes the accent, the way the eye looks for it.
class _EnTeteDeJour extends StatelessWidget {
  const _EnTeteDeJour({required this.jour, required this.aujourdhui});

  final DateTime jour;
  final DateTime aujourdhui;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final l = L.of(context);
    final langue = langueDesDates(context);
    // Counted on calendar dates, not hours: a day with a clock change lasts 23 or 25.
    final ecart = DateTime.utc(jour.year, jour.month, jour.day)
        .difference(
          DateTime.utc(aujourdhui.year, aujourdhui.month, aujourdhui.day),
        )
        .inDays;
    final nom = switch (ecart) {
      0 => l.aujourdHui,
      1 => l.demain,
      -1 => l.hier,
      _ => DateFormat.EEEE(langue).format(jour),
    };
    final estAujourdhui = ecart == 0;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Mesures.marge),
      child: Text.rich(
        TextSpan(
          children: [
            TextSpan(
              text: nom.toUpperCase(),
              style: TextStyle(
                fontWeight: FontWeight.w800,
                letterSpacing: 0.4,
                color: estAujourdhui ? gc.accentTexte : gc.encre,
              ),
            ),
            TextSpan(
              text: '  ${DateFormat.yMd(langue).format(jour)}',
              style: TextStyle(
                fontWeight: FontWeight.w500,
                color: estAujourdhui ? gc.accentTexte : gc.estompe,
              ),
            ),
          ],
        ),
        style: const TextStyle(fontSize: 15),
      ),
    );
  }
}

/// A task: an open box, its due date in red when it is late, the title.
class _LigneDeTache extends StatelessWidget {
  const _LigneDeTache({
    required this.tache,
    required this.jour,
    required this.surTache,
    required this.maintenant,
  });

  final Tache tache;

  /// The day whose section lists the task.
  final DateTime jour;
  final ValueChanged<Tache> surTache;
  final DateTime maintenant;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final l = L.of(context);
    final langue = langueDesDates(context);
    final (titre, style) = switch (tache.provenance) {
      ProvenanceDuTitre.illisible => (
        l.contenuIllisible,
        TextStyle(color: gc.danger, fontStyle: FontStyle.italic),
      ),
      ProvenanceDuTitre.sansTitre => (
        l.sansTitre,
        TextStyle(color: gc.estompe, fontStyle: FontStyle.italic),
      ),
      _ => (tache.titre, TextStyle(color: gc.encre)),
    };
    final echeance = tache.echeance;
    // The due date is said only when it is not the section's own day: a late task
    // gathered under today, in red.
    final enRetard =
        echeance != null &&
        !memeJour(echeance, jour) &&
        echeance.isBefore(minuit(maintenant));
    return InkWell(
      key: Key('tache.${tache.id}'),
      onTap: () => surTache(tache),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Mesures.marge, 7, Mesures.marge, 7),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Semantics(
              checked: false,
              label: titre,
              child: Container(
                width: 20,
                height: 20,
                margin: const EdgeInsets.only(top: 1, right: 12),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(5),
                  border: Border.all(color: gc.succes, width: 2),
                ),
              ),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (enRetard)
                    Text(
                      DateFormat.MMMd(langue).format(echeance),
                      style: TextStyle(
                        color: gc.danger,
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  Text(titre, style: style.copyWith(fontSize: 16)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// An event: its time on the left, a bar in its calendar's colour, the title and what
/// else is known — type of booking, place — beneath.
class _LigneDEvenement extends StatelessWidget {
  const _LigneDEvenement({
    required this.ligne,
    required this.jour,
    required this.couleur,
    required this.surLigne,
  });

  final LigneDAgenda ligne;
  final DateTime jour;
  final Color couleur;
  final ValueChanged<LigneDAgenda> surLigne;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final l = L.of(context);
    final (titre, style) = titreAffiche(context, ligne, gc);
    final details = [
      if (ligne.invite != null && ligne.titre.isNotEmpty) ligne.titre,
      if (ligne.lieu != null) ligne.lieu!,
    ];
    // An event that started before this day shows from midnight: "09:00" on the third
    // day of a conference would be the first day's hour.
    final commenceCeJour = memeJour(ligne.debut, jour);
    final finitCeJour =
        memeJour(ligne.fin, jour) ||
        ligne.fin.isAtSameMomentAs(plusJours(minuit(jour), 1));
    return InkWell(
      key: Key('ligne.${ligne.id}'),
      onTap: () => surLigne(ligne),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Mesures.marge, 6, Mesures.marge, 6),
        child: IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SizedBox(
                width: 52,
                child: ligne.journeeEntiere
                    ? Text(
                        l.journee,
                        style: TextStyle(
                          fontSize: 12,
                          color: gc.estompe,
                          height: 1.6,
                        ),
                      )
                    : Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            heureCourte(
                              context,
                              commenceCeJour ? ligne.debut : minuit(jour),
                            ),
                            style: TextStyle(
                              fontSize: 13,
                              height: 1.45,
                              fontWeight: FontWeight.w600,
                              color: gc.encre,
                            ),
                          ),
                          Text(
                            finitCeJour ? heureCourte(context, ligne.fin) : '…',
                            style: TextStyle(fontSize: 12, color: gc.estompe),
                          ),
                        ],
                      ),
              ),
              Container(
                width: 4,
                margin: const EdgeInsets.only(right: 10),
                decoration: BoxDecoration(
                  color: couleur,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      titre,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: style.copyWith(
                        fontSize: 16,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    if (details.isNotEmpty)
                      Text(
                        details.join(' · '),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontSize: 13, color: gc.estompe),
                      ),
                  ],
                ),
              ),
              if (ligne.evenement == null)
                Padding(
                  padding: const EdgeInsets.only(left: 8),
                  child: Icon(Icons.lock_outline, size: 14, color: gc.estompe),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
