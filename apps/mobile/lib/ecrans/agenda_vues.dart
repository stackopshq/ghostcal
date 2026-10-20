import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../l10n/generated/app_localisations.dart';
import '../outils/calendrier.dart';
import '../outils/couloirs.dart';
import '../outils/dates.dart';
import '../services/agenda.dart';
import '../services/taches.dart';
import '../theme.dart';
import 'agenda_jours.dart' show tachesDuJour;

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
(String, TextStyle) titreAffiche(
  BuildContext context,
  LigneDAgenda ligne,
  Gc gc,
) => switch (ligne.invite) {
  final nom? when nom.isNotEmpty => (nom, TextStyle(color: gc.encre)),
  _ => _titreSansInvite(context, ligne, gc),
};

(String, TextStyle) _titreSansInvite(
  BuildContext context,
  LigneDAgenda ligne,
  Gc gc,
) => switch (ligne.provenance) {
  ProvenanceDuTitre.dechiffre ||
  ProvenanceDuTitre.enClair => (ligne.titre, TextStyle(color: gc.encre)),
  ProvenanceDuTitre.illisible => (
    L.of(context).contenuIllisible,
    TextStyle(color: gc.danger, fontStyle: FontStyle.italic),
  ),
  ProvenanceDuTitre.sansTitre => (
    L.of(context).sansTitre,
    TextStyle(color: gc.estompe, fontStyle: FontStyle.italic),
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
    this.taches = const [],
    this.surTache,
  });

  final List<DateTime> jours;
  final List<LigneDAgenda> lignes;
  final CouleurDe couleurDe;
  final ValueChanged<LigneDAgenda> surLigne;

  /// Tapping an empty slot: the start of the half hour that was tapped.
  final ValueChanged<DateTime>? surCreneau;

  /// Tapping a day header (week view): open that day.
  final ValueChanged<DateTime>? surJour;

  /// Tasks, shown in the strip above the hours on the day they are due (today also
  /// gathers the overdue ones), as in Fantastical.
  final List<Tache> taches;
  final ValueChanged<Tache>? surTache;

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
    final maintenant = DateTime.now();
    final journees = [
      for (final j in widget.jours)
        widget.lignes.where((l) => l.journeeEntiere && couvre(l, j)).toList(),
    ];
    final taches = [
      for (final j in widget.jours)
        tachesDuJour(widget.taches, j, maintenant: maintenant),
    ];
    final iAujourdhui = widget.jours.indexWhere((j) => memeJour(j, maintenant));
    return LayoutBuilder(
      builder: (context, dehors) {
        // A phone held sideways: the header goes on one line and the strip keeps one
        // item a day, or the hours — what the view is for — would have no room left.
        final court = dehors.maxHeight < 450;
        return Column(
          children: [
            if (semaine) _entete(context, gc, court: court),
            if (journees.any((j) => j.isNotEmpty) ||
                taches.any((t) => t.isNotEmpty))
              _bandeauDesJournees(
                context,
                gc,
                journees,
                taches,
                visibles: court ? 1 : 3,
              ),
            Divider(height: 1, color: gc.bordure),
            Expanded(
              child: SingleChildScrollView(
                controller: _defilement,
                child: SizedBox(
                  height: 24 * _hauteurDHeure,
                  child: LayoutBuilder(
                    builder: (context, contraintes) => Stack(
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            _heures(context, gc, maintenant, iAujourdhui >= 0),
                            for (final jour in widget.jours)
                              Expanded(
                                child: ColoredBox(
                                  // Today's column is tinted in a week, the way the eye
                                  // looks for it before reading any date.
                                  color: semaine && memeJour(jour, maintenant)
                                      ? Gc.neon.withValues(
                                          alpha: gc.sombre ? 0.10 : 0.06,
                                        )
                                      : Colors.transparent,
                                  child: _colonne(context, gc, jour),
                                ),
                              ),
                          ],
                        ),
                        if (iAujourdhui >= 0)
                          _ligneDeMaintenant(
                            context,
                            gc,
                            maintenant,
                            colonne: iAujourdhui,
                            largeurDeColonne:
                                (contraintes.maxWidth - _gouttiere) /
                                widget.jours.length,
                          ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  /// The "now" line: the time in red in the gutter, a line across every day of the
  /// grid, and a dot where it crosses today — Fantastical's reading of the hour.
  Widget _ligneDeMaintenant(
    BuildContext context,
    Gc gc,
    DateTime maintenant, {
    required int colonne,
    required double largeurDeColonne,
  }) {
    final y = (maintenant.hour * 60 + maintenant.minute) / 60 * _hauteurDHeure;
    return Positioned(
      top: y - 7,
      left: 0,
      right: 0,
      height: 14,
      child: IgnorePointer(
        child: Stack(
          children: [
            Positioned(
              left: 0,
              width: _gouttiere - 4,
              top: 0,
              bottom: 0,
              child: Align(
                alignment: Alignment.centerRight,
                child: Text(
                  heureCourte(context, maintenant),
                  key: const Key('grille.maintenant'),
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    color: gc.danger,
                  ),
                ),
              ),
            ),
            Positioned(
              left: _gouttiere,
              right: 0,
              top: 6.25,
              height: 1.5,
              child: ColoredBox(color: gc.danger),
            ),
            Positioned(
              left: _gouttiere + colonne * largeurDeColonne - 5,
              top: 2,
              width: 10,
              height: 10,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: gc.danger,
                  shape: BoxShape.circle,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _entete(BuildContext context, Gc gc, {bool court = false}) {
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
                onTap: widget.surJour == null
                    ? null
                    : () => widget.surJour!(jour),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Flex(
                    direction: court ? Axis.horizontal : Axis.vertical,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        DateFormat.E(langue).format(jour).toUpperCase(),
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w500,
                          color: memeJour(jour, maintenant)
                              ? Gc.neon
                              : gc.estompe,
                        ),
                      ),
                      const SizedBox(height: 2, width: 6),
                      _numero(
                        gc,
                        jour,
                        aujourdhui: memeJour(jour, maintenant),
                        taille: court ? 24 : 30,
                      ),
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
    BuildContext context,
    Gc gc,
    List<List<LigneDAgenda>> journees,
    List<List<Tache>> taches, {
    required int visibles,
  }) {
    // A few items a day at most, tasks first: the strip is a summary, and "+N" says
    // what it leaves out.
    return Padding(
      padding: const EdgeInsets.only(left: _gouttiere, bottom: 4, top: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (var i = 0; i < journees.length; i++)
            Expanded(
              child: Column(
                children: [
                  for (final t in taches[i].take(visibles))
                    _puceDeTache(context, gc, t),
                  for (final ligne in journees[i].take(
                    (visibles - taches[i].length).clamp(0, visibles),
                  ))
                    _puce(context, gc, ligne),
                  if (taches[i].length + journees[i].length > visibles)
                    Text(
                      L
                          .of(context)
                          .autresEvenements(
                            taches[i].length + journees[i].length - visibles,
                          ),
                      style: TextStyle(fontSize: 10, color: gc.estompe),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  /// A task in the strip: an open box and the title, on a green tint. Tapping it ticks
  /// it, as in the day list.
  Widget _puceDeTache(BuildContext context, Gc gc, Tache tache) {
    final titre = switch (tache.provenance) {
      ProvenanceDuTitre.illisible => L.of(context).contenuIllisible,
      ProvenanceDuTitre.sansTitre => L.of(context).sansTitre,
      _ => tache.titre,
    };
    return GestureDetector(
      key: Key('bandeau.tache.${tache.id}'),
      onTap: widget.surTache == null ? null : () => widget.surTache!(tache),
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 1, vertical: 1),
        padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 3),
        width: double.infinity,
        decoration: BoxDecoration(
          color: gc.succes.withValues(alpha: gc.sombre ? 0.22 : 0.14),
          borderRadius: BorderRadius.circular(6),
        ),
        child: Row(
          children: [
            Container(
              width: 10,
              height: 10,
              margin: const EdgeInsets.only(right: 4),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(2.5),
                border: Border.all(color: gc.succes, width: 1.5),
              ),
            ),
            Expanded(
              child: Text(
                titre,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: gc.succes,
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
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
        child: Text(
          titre,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: style.copyWith(
            color: Colors.white,
            fontSize: 11,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }

  Widget _heures(
    BuildContext context,
    Gc gc,
    DateTime maintenant,
    bool aujourdhui,
  ) {
    final minutes = maintenant.hour * 60 + maintenant.minute;
    return SizedBox(
      width: _gouttiere,
      child: Stack(
        children: [
          for (var h = 1; h < 24; h++)
            // The hour the red time would sit on is left out: two labels on one line
            // read as neither.
            if (!aujourdhui || (minutes - h * 60).abs() > 15)
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
    final h = _hauteurDHeure;

    return LayoutBuilder(
      builder: (context, contraintes) {
        final largeur = contraintes.maxWidth;
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapUp: widget.surCreneau == null
              ? null
              : (details) {
                  final minutes = (details.localPosition.dy / h * 60).floor();
                  final arrondi = minutes - minutes % 30;
                  widget.surCreneau!(
                    debutDuJour.add(Duration(minutes: arrondi)),
                  );
                },
          child: Stack(
            children: [
              Positioned.fill(
                child: CustomPaint(
                  painter: _Lignes(h, gc.bordure, gauche: true),
                ),
              ),
              for (var i = 0; i < horaires.length; i++)
                _bloc(
                  context,
                  gc,
                  horaires[i],
                  boites[i],
                  couloirs[i],
                  debutDuJour,
                  largeur,
                ),
            ],
          ),
        );
      },
    );
  }

  Widget _bloc(
    BuildContext context,
    Gc gc,
    LigneDAgenda ligne,
    ({DateTime debut, DateTime fin}) boite,
    Couloir couloir,
    DateTime debutDuJour,
    double largeur,
  ) {
    final h = _hauteurDHeure;
    final haut = boite.debut.difference(debutDuJour).inMinutes / 60 * h;
    final hauteur = boite.fin.difference(boite.debut).inMinutes / 60 * h;
    final largeurDeCouloir = largeur / couloir.couloirs;
    final couleur = widget.couleurDe(ligne);
    final (titre, style) = titreAffiche(context, ligne, gc);
    // ─── Étroit, c'est une largeur, pas un nombre de jours ───
    //
    // La condition était `jours.length > 1` : toute vue de semaine passait en 9,5 points
    // et perdait sa ligne d'horaire, quelle que soit la place disponible. C'était juste
    // tant que la largeur était bornée à 560 — sept colonnes y font 72 points. Dans une
    // fenêtre de Mac, la même semaine a 150 points par jour et se lirait comme la vue du
    // jour ; elle restait en caractères de téléphone.
    //
    // Le seuil porte sur le **couloir** et non sur la colonne : deux rendez-vous qui se
    // chevauchent partagent la largeur, et c'est la moitié obtenue qui décide si le titre
    // tient. 110 points est ce qu'il faut pour deux mots de douze points et la marge.
    final etroit = largeurDeCouloir < 110;
    // L'horaire sous le titre : seulement dans un bloc assez haut et assez large. Nommé
    // ici parce que le **budget de lignes** ci-dessous doit lui réserver sa place.
    final avecHoraire = hauteur > 34 && !etroit;
    return Positioned(
      top: haut,
      height: hauteur,
      left: couloir.couloir * largeurDeCouloir + 1,
      width: largeurDeCouloir - 2,
      child: GestureDetector(
        onTap: () => widget.surLigne(ligne),
        child: Container(
          padding: etroit
              ? const EdgeInsets.fromLTRB(3, 2, 1, 1)
              : const EdgeInsets.fromLTRB(5, 3, 3, 2),
          decoration: BoxDecoration(
            color: couleur.withValues(alpha: gc.sombre ? 0.32 : 0.18),
            borderRadius: BorderRadius.circular(6),
            border: Border(left: BorderSide(color: couleur, width: 3)),
          ),
          child: ClipRect(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // ─── `Flexible`, et plus d'arithmétique à tenir ───
                //
                // Le titre prend ce que la ligne d'horaire laisse, et la mise en page le
                // calcule elle-même. Soustraire les hauteurs à la main marchait à onze
                // pixels près, puis à un tiers de pixel près — et un tiers de pixel
                // suffit à peindre les barres de débordement. Un budget qu'on recopie est
                // un budget qui dérive ; celui-ci n'existe plus.
                //
                // `maxLines` reste, mais comme **plafond de lisibilité** et non comme
                // calcul de place : au-delà de six lignes un bloc devient un paragraphe.
                Flexible(
                  child: Text(
                    titre,
                    maxLines: ((hauteur - _margesDuBloc) / (etroit ? 13 : 16))
                        .floor()
                        .clamp(1, 6),
                    overflow: TextOverflow.ellipsis,
                    style: style.copyWith(
                      fontSize: etroit ? 9.5 : 12,
                      height: 1.2,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                if (avecHoraire)
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

/// Les marges verticales d'un bloc. Le plafond de lignes du titre les retire — c'est tout
/// ce qui reste d'arithmétique ici, et elle ne décide plus de la place : `Flexible` s'en
/// charge.
const _margesDuBloc = 5.0;

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

/// A day number. Today is a filled disc in the brand blue wherever it appears, so the
/// eye finds it in a grid of numbers; the selected day, when it is another one, is a
/// disc in the ink colour.
Widget _numero(
  Gc gc,
  DateTime jour, {
  required bool aujourdhui,
  bool selection = false,
  bool estompe = false,
  double taille = 30,
}) {
  final plein = aujourdhui || selection;
  return Container(
    width: taille,
    height: taille,
    alignment: Alignment.center,
    decoration: BoxDecoration(
      shape: BoxShape.circle,
      color: aujourdhui ? Gc.neon : (selection ? gc.encre : null),
    ),
    child: Text(
      '${jour.day}',
      style: TextStyle(
        fontSize: taille * 0.5,
        fontWeight: plein ? FontWeight.w700 : FontWeight.w500,
        color: aujourdhui
            ? Gc.surAccent
            : selection
            ? gc.base
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
    mainAxisSize: MainAxisSize.min,
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
                      Text(
                        DateFormat.E(langue).format(jour).toUpperCase(),
                        style: TextStyle(fontSize: 10, color: gc.estompe),
                      ),
                      const SizedBox(height: 2),
                      _numero(
                        gc,
                        jour,
                        aujourdhui: memeJour(jour, maintenant),
                        selection: memeJour(jour, selection),
                      ),
                      const SizedBox(height: 3),
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
    );
  }
}

/// ─── Combien de titres une case du mois peut porter ───
///
/// Zéro veut dire « des pastilles », et c'est le cas du téléphone : sept colonnes dans
/// 390 points font 54 points par jour, où un titre ne tient pas — il ne resterait qu'une
/// ellipse. La grille y garde donc ses pastilles, et la liste du jour sous elle.
///
/// La fonction est **pure et sortie du widget** pour que l'écran puisse décider, avec la
/// même mesure, s'il montre encore cette liste : les titres dans la grille la rendent
/// redondante, et deux règles séparées divergeraient le jour où l'une change.
///
/// Les deux dimensions comptent, et pas pour la même raison :
///
/// - la **largeur** décide s'il y a de quoi lire — 90 points est le minimum pour deux
///   mots de onze points et la pastille de couleur qui les précède ;
/// - la **hauteur** décide combien, une fois le numéro du jour placé.
///
/// Bornée à cinq : au-delà, une case devient un écran à elle seule, et ce qui dépasse se
/// dit par « +N », comme chez Fantastical.
int titresParCaseDuMois(Size grille) {
  final largeurDeCase = (grille.width - 12) / 7;
  if (largeurDeCase < 90) return 0;
  // 18 pour l'en-tête des jours de la semaine et son écart, puis six rangées.
  final hauteurDeCase = (grille.height - 18) / 6;
  // Les mêmes mesures que la case applique — voir `GrilleDuMois._hauteurDuNumero` et
  // `_hauteurDUneLigne`. Ici elles ne servent qu'à trancher « pastilles ou titres » : le
  // **nombre** se recalcule dans la case, sur sa hauteur réelle, ligne « +N » comprise.
  final tiennent = ((hauteurDeCase - 32) / 14).floor();
  return tiennent.clamp(0, 5);
}

/// The month grid: six weeks, the selected day outlined, and the days' contents —
/// titles when the cells are big enough to read them, dots otherwise.
class GrilleDuMois extends StatelessWidget {
  const GrilleDuMois({
    super.key,
    required this.mois,
    required this.jours,
    required this.selection,
    required this.lignes,
    required this.couleurDe,
    required this.surJour,
    this.titresParCase = 0,
  });

  /// Any date in the month shown.
  final DateTime mois;
  final List<DateTime> jours;
  final DateTime selection;
  final List<LigneDAgenda> lignes;
  final CouleurDe couleurDe;
  final ValueChanged<DateTime> surJour;

  /// Combien de titres chaque case affiche, zéro pour des pastilles — voir
  /// [titresParCaseDuMois]. Donné par l'écran, qui l'emploie aussi pour décider du sort
  /// de la liste du jour.
  final int titresParCase;

  bool get _avecTitres => titresParCase > 0;

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
                    child: Text(
                      DateFormat.E(langue).format(j).toUpperCase(),
                      style: TextStyle(
                        fontSize: 11,
                        letterSpacing: 0.3,
                        fontWeight: FontWeight.w500,
                        // The weekday of today, in its blue: where today falls in the
                        // week reads before any number does.
                        color: j.weekday == maintenant.weekday
                            ? Gc.neon
                            : gc.estompe,
                      ),
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 4),
          for (var semaine = 0; semaine < 6; semaine++)
            // ─── Les rangées prennent la hauteur qu'on leur donne ───
            //
            // Elles valaient 50 points, quelle que soit la fenêtre : un reste de
            // téléphone. Sur un Mac, la grille occupait trois cents points en haut et
            // laissait le reste vide — c'est ce que la comparaison avec Fantastical a
            // rendu évident. `Expanded` ici, et la grille remplit ce qu'elle a.
            //
            // En mode pastilles, l'écran borne la grille lui-même : sans quoi six rangées
            // étirées sur un téléphone donneraient des cases hautes et vides, ce qui est
            // l'autre façon de mal occuper la place.
            Expanded(
              child: _rangee(
                gc,
                // The selected week is a band, as in Fantastical: the list under the
                // grid starts in it, and the band says where.
                bande:
                    !_avecTitres &&
                    jours
                        .skip(semaine * 7)
                        .take(7)
                        .any((j) => memeJour(j, selection)),
                child: Row(
                  children: [
                    for (final jour in jours.skip(semaine * 7).take(7))
                      Expanded(
                        child: InkWell(
                          key: Key('mois.${jour.month}.${jour.day}'),
                          borderRadius: BorderRadius.circular(
                            _avecTitres ? 6 : 12,
                          ),
                          onTap: () => surJour(jour),
                          child: _case(context, gc, jour, maintenant),
                        ),
                      ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _rangee(Gc gc, {required bool bande, required Widget child}) => bande
      ? DecoratedBox(
          decoration: BoxDecoration(
            color: gc.surface2,
            borderRadius: BorderRadius.circular(Mesures.rayon),
          ),
          child: child,
        )
      : child;

  Widget _case(
    BuildContext context,
    Gc gc,
    DateTime jour,
    DateTime maintenant,
  ) {
    final numero = _numero(
      gc,
      jour,
      aujourdhui: memeJour(jour, maintenant),
      selection: memeJour(jour, selection),
      estompe: jour.month != mois.month,
    );

    if (!_avecTitres) {
      // Scaled down, never cut: a phone held sideways leaves rows lower than the
      // number and its dots, and a dot spilling into the next week reads as that day's.
      return FittedBox(
        fit: BoxFit.scaleDown,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            numero,
            const SizedBox(height: 3),
            _points([
              for (final l in lignes.where((l) => couvre(l, jour)))
                couleurDe(l),
            ]),
          ],
        ),
      );
    }

    final duJour = lignes.where((l) => couvre(l, jour)).toList()
      ..sort(Agenda.comparerLesLignes);

    // ─── Le compte se refait **ici**, sur la hauteur réelle de la case ───
    //
    // `titresParCase` vient d'une estimation faite sur la grille entière, et elle décide
    // du mode — pastilles ou titres. Elle ne peut pas décider du **nombre** : elle
    // ignorait la ligne « +N », et une case pleine débordait de six pixels, c'est-à-dire
    // peignait les barres jaunes et noires de Flutter en travers du mois. Vu seulement
    // quand un jour portait assez d'événements pour remplir sa case.
    //
    // `LayoutBuilder` donne la hauteur que la case a vraiment, et le compte en découle —
    // y compris la ligne de débordement, qui prend la place d'un titre quand elle paraît.
    // Plus d'arithmétique à tenir en double.
    final cetteCase = LayoutBuilder(
      builder: (context, contraintes) {
        final place = contraintes.maxHeight - _hauteurDuNumero;
        final tiennent = (place / _hauteurDUneLigne).floor().clamp(0, 8);
        var montres = duJour.take(tiennent).toList();
        var reste = duJour.length - montres.length;
        if (reste > 0) {
          // « +N » occupe une ligne : elle se prend sur les titres, pas sur le vide.
          montres = duJour.take((tiennent - 1).clamp(0, tiennent)).toList();
          reste = duJour.length - montres.length;
        }
        return _contenuDeCase(context, gc, numero, montres, reste);
      },
    );
    // Today's cell is tinted, so today reads before its number does.
    return memeJour(jour, maintenant)
        ? ColoredBox(
            color: Gc.neon.withValues(alpha: gc.sombre ? 0.16 : 0.08),
            child: cetteCase,
          )
        : cetteCase;
  }

  /// Hauteurs réelles, nommées une fois : [titresParCaseDuMois] les estime pour choisir le
  /// mode, la case les applique pour choisir le nombre. Deux usages, une seule source.
  static const _hauteurDuNumero = 32.0;
  static const _hauteurDUneLigne = 14.0;

  Widget _contenuDeCase(
    BuildContext context,
    Gc gc,
    Widget numero,
    List<LigneDAgenda> montres,
    int reste,
  ) {
    return Container(
      // Un filet en haut de chaque case : sans lui, des titres alignés sur sept colonnes
      // se lisent comme une seule liste en désordre. C'est ce que dessine tout agenda qui
      // écrit dans ses cases, et ça ne coûte qu'un trait.
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: gc.bordure)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 2),
      // La ceinture, après les bretelles : si une mesure dérive d'un demi-pixel — une
      // police système qui change, une densité différente —, la case rogne au lieu de
      // peindre un avertissement de débordement en travers de l'agenda.
      child: ClipRect(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Le numéro n'est plus centré : il tient le coin, et les titres commencent
            // sous lui. Centré, il laisserait une colonne de vide de part et d'autre.
            numero,
            for (final ligne in montres) _titreDeCase(context, gc, ligne),
            // `+N`, et non les N titres suivants écrasés : une case qui déborde doit le
            // dire, pas le cacher derrière trois ellipses.
            if (reste > 0)
              SizedBox(
                height: _hauteurDUneLigne,
                child: Padding(
                  padding: const EdgeInsets.only(left: 2),
                  child: Text(
                    L.of(context).autresEvenements(reste),
                    style: TextStyle(fontSize: 10, color: gc.estompe),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  /// Un titre dans une case : la pastille de son calendrier, puis le texte sur une ligne.
  ///
  /// Le style vient de [titreAffiche] et non d'une constante : un contenu que la clé
  /// n'ouvre pas doit se lire « Contenu illisible » en rouge **ici aussi**. La grille du
  /// mois est souvent le premier écran qu'on regarde ; y masquer ce cas le ferait
  /// découvrir ailleurs, ou jamais.
  Widget _titreDeCase(BuildContext context, Gc gc, LigneDAgenda ligne) {
    final (titre, style) = titreAffiche(context, ligne, gc);
    // An all-day item is a band in its colour, a timed one a dot and a title: the
    // two read apart at a glance, as in Fantastical.
    if (ligne.journeeEntiere) {
      final couleur = couleurDe(ligne);
      return Container(
        height: 14,
        margin: const EdgeInsets.only(bottom: 0),
        padding: const EdgeInsets.only(left: 3),
        decoration: BoxDecoration(
          color: couleur.withValues(alpha: gc.sombre ? 0.30 : 0.18),
          border: Border(left: BorderSide(color: couleur, width: 2.5)),
        ),
        alignment: Alignment.centerLeft,
        child: Text(
          titre,
          maxLines: 1,
          overflow: TextOverflow.clip,
          softWrap: false,
          style: style.copyWith(fontSize: 11, height: 1.1),
        ),
      );
    }
    return SizedBox(
      height: 14,
      child: Row(
        children: [
          Container(
            width: 5,
            height: 5,
            margin: const EdgeInsets.only(right: 3),
            decoration: BoxDecoration(
              color: couleurDe(ligne),
              shape: BoxShape.circle,
            ),
          ),
          Expanded(
            child: Text(
              titre,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: style.copyWith(fontSize: 11, height: 1.1),
            ),
          ),
        ],
      ),
    );
  }
}
