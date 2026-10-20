import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../l10n/generated/app_localisations.dart';
import '../outils/calendrier.dart';
import '../outils/dates.dart';
import '../services/agenda.dart';
import '../services/erreurs.dart';
import '../theme.dart';
import 'agenda_jours.dart';
import 'agenda_vues.dart';

/// Searching the agenda, on the device.
///
/// The server cannot search: it never reads a title. So the screen fetches a year
/// around today — the widest window the server allows — opens it here, and filters as
/// the user types. Nothing typed leaves the phone.
class EcranDeRecherche extends StatefulWidget {
  const EcranDeRecherche({
    super.key,
    required this.agenda,
    required this.organisation,
    required this.couleurDe,
    required this.surLigne,
    required this.visible,
  });

  final Agenda agenda;
  final String organisation;
  final CouleurDe couleurDe;
  final ValueChanged<LigneDAgenda> surLigne;

  /// The calendar filter of the agenda: what is hidden there stays hidden here.
  final bool Function(LigneDAgenda) visible;

  @override
  State<EcranDeRecherche> createState() => _EcranDeRechercheState();
}

/// Six months each way: 360 days, under the server's 366-day bound.
const _demiFenetre = 180;

/// Lower case without accents, so "reunion" finds "Réunion".
String normaliserPourLaRecherche(String texte) {
  const accents = {
    'à': 'a',
    'â': 'a',
    'ä': 'a',
    'á': 'a',
    'ã': 'a',
    'ç': 'c',
    'é': 'e',
    'è': 'e',
    'ê': 'e',
    'ë': 'e',
    'î': 'i',
    'ï': 'i',
    'í': 'i',
    'ì': 'i',
    'ô': 'o',
    'ö': 'o',
    'ó': 'o',
    'ò': 'o',
    'õ': 'o',
    'ù': 'u',
    'û': 'u',
    'ü': 'u',
    'ú': 'u',
    'ÿ': 'y',
    'ñ': 'n',
    'œ': 'oe',
    'æ': 'ae',
  };
  final bas = texte.toLowerCase();
  final sortie = StringBuffer();
  for (final c in bas.split('')) {
    sortie.write(accents[c] ?? c);
  }
  return sortie.toString();
}

/// Whether [ligne] matches every word of [requete], in its title, place or invitee.
bool correspond(LigneDAgenda ligne, String requete) {
  final mots = normaliserPourLaRecherche(requete)
      .split(RegExp(r'\s+'))
      .where((m) => m.isNotEmpty);
  if (mots.isEmpty) return false;
  final texte = normaliserPourLaRecherche(
    [ligne.titre, ligne.lieu ?? '', ligne.invite ?? ''].join(' '),
  );
  return mots.every(texte.contains);
}

class _EcranDeRechercheState extends State<EcranDeRecherche> {
  final _champ = TextEditingController();
  List<LigneDAgenda>? _lignes;
  String? _erreur;

  @override
  void initState() {
    super.initState();
    _charger();
    _champ.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _champ.dispose();
    super.dispose();
  }

  Future<void> _charger() async {
    final aujourdhui = minuit(DateTime.now());
    try {
      final lignes = await widget.agenda.lignes(
        de: plusJours(aujourdhui, -_demiFenetre),
        a: plusJours(aujourdhui, _demiFenetre),
        organisation: widget.organisation,
      );
      if (mounted) {
        setState(() => _lignes = lignes.where(widget.visible).toList());
      }
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, L.of(context)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final l = L.of(context);
    final requete = _champ.text.trim();
    final trouvees = requete.isEmpty || _lignes == null
        ? const <LigneDAgenda>[]
        : (_lignes!.where((x) => correspond(x, requete)).toList()
            ..sort(Agenda.comparerLesLignes));
    // A pushed route: nothing paints the background under it but itself.
    return FondGhost(
      child: Scaffold(
        appBar: AppBar(
          titleSpacing: 0,
          title: TextField(
            key: const Key('recherche.champ'),
            controller: _champ,
            autofocus: true,
            textInputAction: TextInputAction.search,
            decoration: InputDecoration(
              hintText: l.rechercherDansLAgenda,
              // The app bar is the field: the theme's outline would draw a box in it.
              border: InputBorder.none,
              enabledBorder: InputBorder.none,
              focusedBorder: InputBorder.none,
              filled: false,
            ),
          ),
        ),
        body: _lignes == null
            ? Center(
                child: _erreur == null
                    ? const CircularProgressIndicator()
                    : Text(_erreur!, style: TextStyle(color: gc.danger)),
              )
            : requete.isEmpty
            ? const SizedBox.shrink()
            : trouvees.isEmpty
            ? Padding(
                padding: const EdgeInsets.all(Mesures.marge),
                child: Text(
                  l.aucunResultat,
                  style: TextStyle(color: gc.estompe),
                ),
              )
            : ListView(
                children: [
                  for (final (i, ligne) in trouvees.indexed) ...[
                    if (i == 0 || !memeJour(trouvees[i - 1].debut, ligne.debut))
                      Padding(
                        padding: const EdgeInsets.fromLTRB(
                          Mesures.marge,
                          16,
                          Mesures.marge,
                          4,
                        ),
                        child: Text(
                          DateFormat.yMMMMEEEEd(langueDesDates(context))
                              .format(ligne.debut)
                              .toUpperCase(),
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 0.3,
                            color: gc.estompe,
                          ),
                        ),
                      ),
                    LigneDEvenement(
                      ligne: ligne,
                      jour: ligne.debut,
                      couleur: widget.couleurDe(ligne),
                      surLigne: widget.surLigne,
                    ),
                  ],
                ],
              ),
      ),
    );
  }
}
