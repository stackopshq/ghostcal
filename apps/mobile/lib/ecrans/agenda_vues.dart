import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../l10n/generated/app_localisations.dart';
import '../outils/calendrier.dart';
import '../outils/couloirs.dart';
import '../outils/dates.dart';
import '../services/agenda.dart';
import '../theme.dart';

/// The building blocks of the agenda views (day, week, month), Fantastical-style.
/// The screen (`agenda.dart`) owns the data and navigation; these widgets only draw.

typedef CouleurDe = Color Function(LigneDAgenda ligne);

/// A time as the device writes it: 24-hour or AM/PM, following the system setting.
String heureCourte(BuildContext context, DateTime d) {
  final langue = langueDesDates(context);
  return MediaQuery.alwaysUse24HourFormatOf(context)
      ? DateFormat.Hm(langue).format(d)
      : DateFormat.jm(langue).format(d);
}

/// The label of an item and how it is styled. What cannot be decrypted is still shown:
/// a missing row reads as "free", which is false and costs a double booking.
/// Ce qu'une ligne annonce, et dans quel style.
///
/// Une réservation est nommée par **qui** l'a prise, pas par le type de rendez-vous : une
/// journée de « RDV en visioconférence » empilés n'apprenait rien, et il fallait ouvrir
/// chaque fiche. Le type ne disparaît pas pour autant, il passe en sous-titre, à côté de
/// l'heure.
(String, TextStyle) titreAffiche(BuildContext context, LigneDAgenda ligne, Gc gc) =>
    switch (ligne.invite) {
      final nom? when nom.isNotEmpty => (nom, TextStyle(color: gc.encre)),
      _ => _titreSansInvite(context, ligne, gc),
    };

(String, TextStyle) _titreSansInvite(BuildContext context, LigneDAgenda ligne, Gc gc) =>
    switch (ligne.provenance) {
      ProvenanceDuTitre.dechiffre ||
      ProvenanceDuTitre.enClair =>
        (ligne.titre, TextStyle(color: gc.encre)),
      ProvenanceDuTitre.illisible => (
          L.of(context).contenuIllisible,
          TextStyle(color: gc.danger, fontStyle: FontStyle.italic)
        ),
      ProvenanceDuTitre.sansTitre => (
          L.of(context).sansTitre,
          TextStyle(color: gc.estompe, fontStyle: FontStyle.italic)
        ),
    };

/// Whether [ligne] covers some of [jour].
bool couvre(LigneDAgenda ligne, DateTime jour) {
  final debut = minuit(jour);
  final fin = plusJours(debut, 1);
  if (ligne.journeeEntiere) {
    return ligne.debut.isBefore(fin) && ligne.fin.isAfter(debut) ||
        memeJour(ligne.debut, jour);
  }
  return ligne.debut.isBefore(fin) && ligne.fin.isAfter(debut);
}

/// Hour grid for one day or a week: all-day strip on top, timed events positioned by
/// time and laid side by side when they overlap, a "now" line on today.
class GrilleHoraire extends StatefulWidget {
  const GrilleHoraire({
    super.key,
    required this.jours,
    required this.lignes,
    required this.couleurDe,
    required this.surLigne,
    this.surCreneau,
    this.surJour,
  });

  final List<DateTime> jours;
  final List<LigneDAgenda> lignes;
  final CouleurDe couleurDe;
  final ValueChanged<LigneDAgenda> surLigne;

  /// Tapping an empty slot: the start of the half hour that was tapped.
  final ValueChanged<DateTime>? surCreneau;

  /// Tapping a day header (week view): open that day.
  final ValueChanged<DateTime>? surJour;

  @override
  State<GrilleHoraire> createState() => _GrilleHoraireState();
}

class _GrilleHoraireState extends State<GrilleHoraire> {
  static const _gouttiere = 52.0;
  late final ScrollController _defilement;
  Timer? _minute;

  double get _hauteurDHeure => widget.jours.length == 1 ? 64 : 52;

  @override
  void initState() {
    super.initState();
    final maintenant = DateTime.now();
    final aujourdhui = widget.jours.any((j) => memeJour(j, maintenant));
    // Open on the current hour today, on the working morning otherwise.
    final heure = aujourdhui ? (maintenant.hour - 1).clamp(0, 16) : 7.5;
    _defilement = ScrollController(initialScrollOffset: heure * _hauteurDHeure);
    // The "now" line moves; a minute is the finest it can show.
    _minute = Timer.periodic(const Duration(minutes: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _minute?.cancel();
    _defilement.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final semaine = widget.jours.length > 1;
    final journees = [
      for (final j in widget.jours)
        widget.lignes.where((l) => l.journeeEntiere && couvre(l, j)).toList(),
    ];
    return Column(
      children: [
        if (semaine) _entete(context, gc),
        if (journees.any((j) => j.isNotEmpty)) _bandeauDesJournees(context, gc, journees),
        Divider(height: 1, color: gc.bordure),
        Expanded(
          child: SingleChildScrollView(
            controller: _defilement,
            child: SizedBox(
              height: 24 * _hauteurDHeure,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _heures(context, gc),
                  for (final jour in widget.jours)
                    Expanded(child: _colonne(context, gc, jour)),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _entete(BuildContext context, Gc gc) {
    final langue = langueDesDates(context);
    final maintenant = DateTime.now();
    return Padding(
      padding: const EdgeInsets.only(left: _gouttiere, top: 4, bottom: 4),
      child: Row(
        children: [
          for (final jour in widget.jours)
            Expanded(
              child: InkWell(
                borderRadius: BorderRadius.circular(10),
                onTap: widget.surJour == null ? null : () => widget.surJour!(jour),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Column(
                    children: [
                      Text(DateFormat.E(langue).format(jour).toUpperCase(),
                          style: TextStyle(fontSize: 10, color: gc.estompe)),
                      const SizedBox(height: 2),
                      _numero(gc, jour, aujourdhui: memeJour(jour, maintenant)),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _bandeauDesJournees(
      BuildContext context, Gc gc, List<List<LigneDAgenda>> journees) {
    return Padding(
      padding: const EdgeInsets.only(left: _gouttiere, bottom: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final lignes in journees)
            Expanded(
              child: Column(
                children: [
                  for (final ligne in lignes.take(2)) _puce(context, gc, ligne),
                  if (lignes.length > 2)
                    Text(L.of(context).autresEvenements(lignes.length - 2),
                        style: TextStyle(fontSize: 10, color: gc.estompe)),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _puce(BuildContext context, Gc gc, LigneDAgenda ligne) {
    final couleur = widget.couleurDe(ligne);
    final (titre, style) = titreAffiche(context, ligne, gc);
    return GestureDetector(
      onTap: () => widget.surLigne(ligne),
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 1, vertical: 1),
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
        width: double.infinity,
        decoration: BoxDecoration(
          color: couleur.withValues(alpha: 0.85),
          borderRadius: BorderRadius.circular(6),
        ),
        child: Text(titre,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: style.copyWith(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600)),
      ),
    );
  }

  Widget _heures(BuildContext context, Gc gc) {
    return SizedBox(
      width: _gouttiere,
      child: Stack(
        children: [
          for (var h = 1; h < 24; h++)
            Positioned(
              top: h * _hauteurDHeure - 7,
              right: 6,
              child: Text(
                heureCourte(context, DateTime(2000, 1, 1, h)),
                style: TextStyle(fontSize: 10, color: gc.estompe),
              ),
            ),
        ],
      ),
    );
  }

  Widget _colonne(BuildContext context, Gc gc, DateTime jour) {
    final debutDuJour = minuit(jour);
    final finDuJour = plusJours(debutDuJour, 1);
    final minimum = const Duration(minutes: 20);
    final horaires = widget.lignes
        .where((l) => !l.journeeEntiere && couvre(l, jour))
        .toList();
    // Lanes are computed on the drawn box (clamped to the day, minimum height), so a
    // short event whose box covers its neighbour is split too.
    final boites = [
      for (final l in horaires)
        () {
          final debut = l.debut.isBefore(debutDuJour) ? debutDuJour : l.debut;
          var fin = l.fin.isAfter(finDuJour) ? finDuJour : l.fin;
          if (fin.difference(debut) < minimum) fin = debut.add(minimum);
          return (debut: debut, fin: fin);
        }(),
    ];
    final couloirs = repartirEnCouloirs(boites);
    final maintenant = DateTime.now();
    final h = _hauteurDHeure;

    return LayoutBuilder(builder: (context, contraintes) {
      final largeur = contraintes.maxWidth;
      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapUp: widget.surCreneau == null
            ? null
            : (details) {
                final minutes = (details.localPosition.dy / h * 60).floor();
                final arrondi = minutes - minutes % 30;
                widget.surCreneau!(debutDuJour.add(Duration(minutes: arrondi)));
              },
        child: Stack(
          children: [
            Positioned.fill(
              child: CustomPaint(painter: _Lignes(h, gc.bordure, gauche: true)),
            ),
            for (var i = 0; i < horaires.length; i++)
              _bloc(context, gc, horaires[i], boites[i], couloirs[i], debutDuJour, largeur),
            if (memeJour(jour, maintenant))
              Positioned(
                top: maintenant.difference(debutDuJour).inMinutes / 60 * h - 4,
                left: 0,
                right: 0,
                child: IgnorePointer(
                  child: Row(
                    children: [
                      Container(
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(color: gc.danger, shape: BoxShape.circle),
                      ),
                      Expanded(child: Container(height: 2, color: gc.danger)),
                    ],
                  ),
                ),
              ),
          ],
        ),
      );
    });
  }

  Widget _bloc(BuildContext context, Gc gc, LigneDAgenda ligne,
      ({DateTime debut, DateTime fin}) boite, Couloir couloir, DateTime debutDuJour, double largeur) {
    final h = _hauteurDHeure;
    final haut = boite.debut.difference(debutDuJour).inMinutes / 60 * h;
    final hauteur = boite.fin.difference(boite.debut).inMinutes / 60 * h;
    final largeurDeCouloir = largeur / couloir.couloirs;
    final couleur = widget.couleurDe(ligne);
    final (titre, style) = titreAffiche(context, ligne, gc);
    final etroit = widget.jours.length > 1;
    return Positioned(
      top: haut,
      height: hauteur,
      left: couloir.couloir * largeurDeCouloir + 1,
      width: largeurDeCouloir - 2,
      child: GestureDetector(
        onTap: () => widget.surLigne(ligne),
        child: Container(
          padding: etroit ? const EdgeInsets.fromLTRB(3, 2, 1, 1) : const EdgeInsets.fromLTRB(5, 3, 3, 2),
          decoration: BoxDecoration(
            color: couleur.withValues(alpha: gc.sombre ? 0.32 : 0.18),
            borderRadius: BorderRadius.circular(6),
            border: Border(left: BorderSide(color: couleur, width: 3)),
          ),
          child: ClipRect(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  titre,
                  // As many lines as the block holds: in a week column a one-line title
                  // read "Point …" for a 45-minute meeting.
                  maxLines: ((hauteur - 4) / (etroit ? 13 : 16)).floor().clamp(1, 6),
                  overflow: TextOverflow.ellipsis,
                  style: style.copyWith(
                      fontSize: etroit ? 9.5 : 12,
                      height: 1.2,
                      fontWeight: FontWeight.w600),
                ),
                if (hauteur > 34 && !etroit)
                  Text(
                    [
                      '${heureCourte(context, ligne.debut)} – ${heureCourte(context, ligne.fin)}',
                      if (ligne.lieu != null) ligne.lieu!,
                    ].join(' · '),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 11, color: gc.estompe),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Lignes extends CustomPainter {
  _Lignes(this.hauteurDHeure, this.couleur, {this.gauche = false});
  final double hauteurDHeure;
  final Color couleur;
  final bool gauche;

  @override
  void paint(Canvas canvas, Size size) {
    final pleine = Paint()
      ..color = couleur
      ..strokeWidth = 0.6;
    final demi = Paint()
      ..color = couleur.withValues(alpha: couleur.a * 0.4)
      ..strokeWidth = 0.5;
    for (var h = 0; h < 24; h++) {
      final y = h * hauteurDHeure;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), pleine);
      final y2 = y + hauteurDHeure / 2;
      canvas.drawLine(Offset(0, y2), Offset(size.width, y2), demi);
    }
    if (gauche) canvas.drawLine(Offset.zero, Offset(0, size.height), pleine);
  }

  @override
  bool shouldRepaint(_Lignes ancien) =>
      ancien.couleur != couleur || ancien.hauteurDHeure != hauteurDHeure;
}

/// A day number: filled when selected, accent-coloured when it is today.
Widget _numero(Gc gc, DateTime jour, {required bool aujourdhui, bool selection = false, bool estompe = false}) {
  return Container(
    width: 30,
    height: 30,
    alignment: Alignment.center,
    decoration: BoxDecoration(
      shape: BoxShape.circle,
      color: selection ? (aujourdhui ? gc.danger : gc.encre) : null,
    ),
    child: Text(
      '${jour.day}',
      style: TextStyle(
        fontSize: 14,
        fontWeight: aujourdhui || selection ? FontWeight.w700 : FontWeight.w500,
        color: selection
            ? gc.base
            : aujourdhui
                ? gc.danger
                : estompe
                    ? gc.estompe.withValues(alpha: 0.6)
                    : gc.encre,
      ),
    ),
  );
}

/// Up to three dots in the colours of a day's items.
Widget _points(List<Color> couleurs) => SizedBox(
      height: 6,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          for (final c in couleurs.take(3))
            Container(
              width: 5,
              height: 5,
              margin: const EdgeInsets.symmetric(horizontal: 1),
              decoration: BoxDecoration(color: c, shape: BoxShape.circle),
            ),
        ],
      ),
    );

/// The week strip above the day view: tap a day to open it, dots show busy days.
class BandeauDeSemaine extends StatelessWidget {
  const BandeauDeSemaine({
    super.key,
    required this.jours,
    required this.selection,
    required this.lignes,
    required this.couleurDe,
    required this.surJour,
  });

  final List<DateTime> jours;
  final DateTime selection;
  final List<LigneDAgenda> lignes;
  final CouleurDe couleurDe;
  final ValueChanged<DateTime> surJour;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final langue = langueDesDates(context);
    final maintenant = DateTime.now();
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
      child: Row(
        children: [
          for (final jour in jours)
            Expanded(
              child: InkWell(
                key: Key('bandeau.${jour.day}'),
                borderRadius: BorderRadius.circular(12),
                onTap: () => surJour(jour),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Column(
                    children: [
                      Text(DateFormat.E(langue).format(jour).toUpperCase(),
                          style: TextStyle(fontSize: 10, color: gc.estompe)),
                      const SizedBox(height: 2),
                      _numero(gc, jour,
                          aujourdhui: memeJour(jour, maintenant),
                          selection: memeJour(jour, selection)),
                      const SizedBox(height: 3),
                      _points([
                        for (final l in lignes.where((l) => couvre(l, jour))) couleurDe(l),
                      ]),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// The month grid: six weeks, dots for busy days, the selected day outlined.
class GrilleDuMois extends StatelessWidget {
  const GrilleDuMois({
    super.key,
    required this.mois,
    required this.jours,
    required this.selection,
    required this.lignes,
    required this.couleurDe,
    required this.surJour,
  });

  /// Any date in the month shown.
  final DateTime mois;
  final List<DateTime> jours;
  final DateTime selection;
  final List<LigneDAgenda> lignes;
  final CouleurDe couleurDe;
  final ValueChanged<DateTime> surJour;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final langue = langueDesDates(context);
    final maintenant = DateTime.now();
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 6),
      child: Column(
        children: [
          Row(
            children: [
              for (final j in jours.take(7))
                Expanded(
                  child: Center(
                    child: Text(DateFormat.E(langue).format(j).toUpperCase(),
                        style: TextStyle(fontSize: 10, color: gc.estompe)),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 4),
          for (var semaine = 0; semaine < 6; semaine++)
            Row(
              children: [
                for (final jour in jours.skip(semaine * 7).take(7))
                  Expanded(
                    child: InkWell(
                      key: Key('mois.${jour.month}.${jour.day}'),
                      borderRadius: BorderRadius.circular(12),
                      onTap: () => surJour(jour),
                      child: SizedBox(
                        height: 50,
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            _numero(gc, jour,
                                aujourdhui: memeJour(jour, maintenant),
                                selection: memeJour(jour, selection),
                                estompe: jour.month != mois.month),
                            const SizedBox(height: 2),
                            _points([
                              for (final l in lignes.where((l) => couvre(l, jour)))
                                couleurDe(l),
                            ]),
                          ],
                        ),
                      ),
                    ),
                  ),
              ],
            ),
        ],
      ),
    );
  }
}
