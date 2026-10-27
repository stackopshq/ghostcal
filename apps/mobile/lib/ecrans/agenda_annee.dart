import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../outils/calendrier.dart';
import '../theme.dart';

/// Les douze mois de l'année, d'un seul coup d'œil.
///
/// ─── Ce qu'elle montre, et ce qu'elle ne montre pas ───
///
/// Des nombres, et rien d'autre : ni pastille, ni titre, ni couleur de calendrier. À
/// cette taille un jour fait dix-huit points — de quoi écrire « 28 », pas de quoi dire
/// ce qu'il contient. Une pastille sous chaque jour chargé donnerait un semis de points
/// qu'on ne sait pas lire, et ferait croire qu'on peut y chercher quelque chose.
///
/// Elle ne charge donc aucun événement. C'est délibéré et c'est dit dans `_fenetre` :
/// douze mois de requête pour ne rien en dessiner, sur la vue la plus large de
/// l'application, se paierait à chaque ouverture.
///
/// ─── Ce à quoi elle sert ───
///
/// À se repérer et à sauter. « La semaine du 12 mai », « le lundi de Pentecôte », « dans
/// combien de temps tombe ce vendredi » : des questions de calendrier mural, auxquelles
/// une liste d'événements ne répond pas. Un clic sur un jour ouvre ce jour.
class GrilleDeLAnnee extends StatelessWidget {
  const GrilleDeLAnnee({
    super.key,
    required this.annee,
    required this.premierJour,
    required this.surJour,
    this.aujourdhui,
  });

  /// N'importe quelle date de l'année montrée.
  final DateTime annee;

  /// Le premier jour de la semaine, tel que la langue du système le veut.
  final int premierJour;

  final ValueChanged<DateTime> surJour;

  /// Le jour à marquer, pour les témoins. `null` en production : c'est alors
  /// `DateTime.now()`.
  ///
  /// ─── Pourquoi une horloge injectable ───
  ///
  /// Le témoin de ce repère lisait `DateTime.now()` comme la vue, donc il n'éprouvait
  /// que **le jour où il tournait**. Il a été vert le 24 octobre 2026 avec le défaut en
  /// place, et rouge le 26 — parce que le défaut ne se voit que si aujourd'hui tombe dans
  /// une semaine partagée par deux mois, ce qui arrive une semaine sur quatre environ.
  ///
  /// Un témoin qui ne mord qu'à certaines dates est pire qu'absent le reste du temps : il
  /// dit que la question est réglée. Et il rend `main` rouge sans qu'une ligne ait changé,
  /// ce qui bloque tout le monde pour une raison que personne ne cherche dans le calendrier.
  final DateTime? aujourdhui;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, contraintes) {
        // Les colonnes suivent la place, et ne descendent jamais sous 250 points par
        // mois : en dessous, « sam. » et « dim. » se chevauchent.
        final colonnes = (contraintes.maxWidth / 250).floor().clamp(1, 4);
        final rangs = (12 / colonnes).ceil();

        // ─── Les douze mois tiennent d'un bloc quand la place existe ───
        //
        // Un rapport fixe donnait une grille qu'il fallait faire défiler même en plein
        // écran : une année qu'on ne voit pas d'un coup d'œil ne sert plus à rien, et
        // c'est tout ce qu'on lui demande. La hauteur se déduit donc de la place
        // disponible, et le défilement ne reparaît que lorsqu'un mois descendrait sous
        // 190 points — en dessous, les nombres se touchent et la grille devient un
        // motif.
        const ecartX = 24.0;
        const ecartY = 28.0;
        final largeurDeCase =
            (contraintes.maxWidth - 32 - ecartX * (colonnes - 1)) / colonnes;
        final hauteurDisponible =
            (contraintes.maxHeight - 28 - ecartY * (rangs - 1)) / rangs;
        final hauteurDeCase = math.max(hauteurDisponible, 190.0);

        return GridView.count(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
          crossAxisCount: colonnes,
          crossAxisSpacing: ecartX,
          mainAxisSpacing: ecartY,
          childAspectRatio: largeurDeCase / hauteurDeCase,
          children: [
            for (final mois in moisDeLAnnee(annee))
              _Mois(
                mois: mois,
                premierJour: premierJour,
                surJour: surJour,
                aujourdhui: aujourdhui,
              ),
          ],
        );
      },
    );
  }
}

class _Mois extends StatelessWidget {
  const _Mois({
    required this.mois,
    required this.premierJour,
    required this.surJour,
    this.aujourdhui,
  });

  final DateTime mois;
  final int premierJour;
  final ValueChanged<DateTime> surJour;
  final DateTime? aujourdhui;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final langue = Localizations.localeOf(context).toLanguageTag();
    final jours = joursDeLaGrilleDuMois(mois, premierJour);
    final leJour = minuit(aujourdhui ?? DateTime.now());

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 6),
          child: Text(
            toBeginningOfSentenceCase(DateFormat.MMMM(langue).format(mois)),
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w600,
              color: gc.accentTexte,
            ),
          ),
        ),
        Row(
          children: [
            for (final jour in jours.take(7))
              Expanded(
                child: Text(
                  // L'initiale seule : « L M M J V S D ». Deux lettres ne tiennent pas
                  // dans dix-huit points, et trois se chevauchent.
                  DateFormat.E(langue)
                      .format(jour)
                      .characters
                      .first
                      .toUpperCase(),
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 10, color: gc.estompe),
                ),
              ),
          ],
        ),
        const SizedBox(height: 2),
        for (var rang = 0; rang < 6; rang++)
          Expanded(
            child: Row(
              children: [
                for (final jour in jours.skip(rang * 7).take(7))
                  Expanded(
                    child: _Jour(
                      jour: jour,
                      duMois: jour.month == mois.month,
                      // `duMois` **et** la date : une grille mensuelle affiche les
                      // jours débordants du mois voisin, et sans la première condition
                      // le jour d'aujourd'hui s'allume dans les **deux** grilles qui le
                      // contiennent. Novembre 2026 commence un dimanche, donc sa
                      // première rangée montre le 26 au 31 octobre.
                      //
                      // Trouvé par la session iOS, sur `main` rouge. Le correctif est
                      // le sien.
                      aujourdhui:
                          jour.month == mois.month && minuit(jour) == leJour,
                      surClic: () => surJour(jour),
                    ),
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

class _Jour extends StatelessWidget {
  const _Jour({
    required this.jour,
    required this.duMois,
    required this.aujourdhui,
    required this.surClic,
  });

  final DateTime jour;
  final bool duMois;
  final bool aujourdhui;
  final VoidCallback surClic;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    // Les jours des mois voisins restent visibles, en gris pâle : les effacer ferait
    // commencer la grille au hasard, et on ne saurait plus quel jour de la semaine
    // ouvre le mois.
    final encre = aujourdhui
        ? Gc.surAccent
        : (duMois ? gc.encre : gc.estompe.withValues(alpha: 0.45));
    return InkWell(
      onTap: duMois ? surClic : null,
      customBorder: const CircleBorder(),
      child: Center(
        child: Container(
          width: 20,
          height: 20,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: aujourdhui ? gc.accentTexte : null,
            shape: BoxShape.circle,
          ),
          child: FittedBox(
            child: Text(
              '${jour.day}',
              style: TextStyle(
                fontSize: 11,
                color: encre,
                fontWeight: aujourdhui ? FontWeight.w700 : FontWeight.w400,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
