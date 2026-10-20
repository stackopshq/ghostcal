import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../l10n/generated/app_localisations.dart';
import '../outils/calendrier.dart';
import '../outils/dates.dart';
import '../services/agenda.dart';
import '../services/erreurs.dart';
import '../services/session.dart';
import '../services/taches.dart';
import '../services/verrouillage.dart';
import '../services/vue_agenda.dart';
import '../theme.dart';
import 'agenda_jours.dart';
import 'agenda_vues.dart';
import 'nouvel_evenement.dart';

/// The agenda, as a day, a week, a month or a list — the user's choice, remembered.
///
/// Each view asks the server for the window it shows and no more: the server bounds the
/// range to 366 days, because a recurring event expanded over an unbounded range would
/// be a denial of service.
class EcranDAgenda extends StatefulWidget {
  const EcranDAgenda({
    super.key,
    required this.session,
    required this.verrouillage,
  });

  final Session session;
  final Verrouillage verrouillage;

  @override
  State<EcranDAgenda> createState() => _EcranDAgendaState();
}

class _EcranDAgendaState extends State<EcranDAgenda> {
  /// Days shown by the list view, from the selected day.
  static const _joursDeLaListe = 30;

  /// La hauteur que la grille prend quand elle n'affiche que des pastilles.
  ///
  /// L'en-tête des jours et son écart, puis six rangées de 50 — les mesures d'avant,
  /// gardées telles quelles : c'est la mise en page du téléphone, et elle était juste.
  static const _hauteurDeLaGrilleEnPastilles = 18.0 + 6 * 46;

  /// Days listed under the compact month, from the selected one.
  static const _joursSousLeMois = 14;

  VueDAgenda _vue = VueDAgenda.jour;
  DateTime _ancre = minuit(DateTime.now());
  ({DateTime de, DateTime a})? _fenetreChargee;
  List<LigneDAgenda>? _lignes;
  List<Calendrier> _calendriers = const [];
  List<Tache> _taches = const [];
  String? _erreur;
  bool _charge = false;
  int _premierJour = 1;

  @override
  void initState() {
    super.initState();
    VueDAgenda.retenue().then((vue) {
      if (!mounted) return;
      setState(() => _vue = vue);
      _recharger();
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Monday in France, Sunday in the US: the week follows the interface language.
    _premierJour = MaterialLocalizations.of(context).firstDayOfWeekIndex;
  }

  Agenda? get _agenda {
    final api = widget.session.api;
    final auth = widget.session.auth;
    if (api == null || auth == null) return null;
    return Agenda(api: api, auth: auth);
  }

  /// The window the current view needs. The day view loads its whole week, so the strip
  /// above it can show which days are busy.
  ({DateTime de, DateTime a}) get _fenetre {
    switch (_vue) {
      case VueDAgenda.jour:
      case VueDAgenda.semaine:
        final debut = debutDeSemaine(_ancre, _premierJour);
        return (de: debut, a: plusJours(debut, 7));
      case VueDAgenda.mois:
        final jours = joursDeLaGrilleDuMois(_ancre, _premierJour);
        return (de: jours.first, a: plusJours(jours.last, 1));
      case VueDAgenda.liste:
        return (de: _ancre, a: plusJours(_ancre, _joursDeLaListe));
    }
  }

  Future<void> _recharger({bool siBesoin = false}) async {
    final fenetre = _fenetre;
    if (siBesoin && fenetre == _fenetreChargee) return;
    final agenda = _agenda;
    final organisation = widget.session.organisation;
    if (agenda == null || organisation == null) return;
    setState(() {
      _charge = true;
      _erreur = null;
    });
    try {
      final taches = _chargerLesTaches(organisation);
      final lignes = await agenda.lignes(
        de: fenetre.de,
        a: fenetre.a,
        organisation: organisation,
      );
      final lesTaches = await taches;
      // Calendars do not change from one period to the next: asked for once.
      if (_calendriers.isEmpty) _calendriers = await agenda.calendriers();
      // A slow answer for a window the user has already left must not overwrite the
      // current one.
      if (mounted && fenetre == _fenetre) {
        setState(() {
          _lignes = lignes;
          if (lesTaches != null) _taches = lesTaches;
          _fenetreChargee = fenetre;
        });
      }
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, L.of(context)));
    } finally {
      if (mounted) setState(() => _charge = false);
    }
  }

  /// The tasks shown among the days. A failure here leaves the previous ones: the
  /// agenda is what this screen is for, and it must not fail because tasks did.
  Future<List<Tache>?> _chargerLesTaches(String organisation) async {
    final api = widget.session.api;
    final auth = widget.session.auth;
    if (api == null || auth == null) return null;
    try {
      return await Taches(
        api: api,
        auth: auth,
      ).lister(organisation: organisation);
    } on Object catch (e) {
      debugPrint('ghostcal.agenda: tasks not loaded: $e');
      return null;
    }
  }

  /// Ticking a task from the agenda: it leaves the list at once, and comes back with
  /// the error if the server refused.
  Future<void> _cocher(Tache tache) async {
    final api = widget.session.api;
    final auth = widget.session.auth;
    if (api == null || auth == null) return;
    final avant = _taches;
    setState(
      () => _taches = [
        for (final t in _taches)
          if (t.id != tache.id) t,
      ],
    );
    try {
      await Taches(api: api, auth: auth).marquer(tache.id, faite: true);
    } on Object catch (e) {
      if (!mounted) return;
      setState(() => _taches = avant);
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(lisible(e, L.of(context)))));
    }
  }

  void _allerA(DateTime jour, {VueDAgenda? vue}) {
    setState(() {
      _ancre = minuit(jour);
      if (vue != null) _vue = vue;
    });
    if (vue != null) vue.retenir();
    _recharger(siBesoin: true);
  }

  void _deplacer(int sens) {
    final cible = switch (_vue) {
      VueDAgenda.jour => plusJours(_ancre, sens),
      VueDAgenda.semaine => plusJours(_ancre, 7 * sens),
      VueDAgenda.mois => plusMois(_ancre, sens),
      VueDAgenda.liste => plusJours(_ancre, _joursDeLaListe * sens),
    };
    _allerA(cible);
  }

  Color _couleurDe(LigneDAgenda ligne) {
    final gc = Gc.of(context);
    if (ligne.source == 'booking') return gc.accentTexte;
    if (ligne.calendrier == null) return gc.estompe;
    final hex = _calendriers
        .where((c) => c.id == ligne.calendrier)
        .map((c) => c.couleur)
        .firstOrNull;
    final valeur = int.tryParse((hex ?? '').replaceFirst('#', ''), radix: 16);
    return valeur == null ? gc.accent : Color(0xFF000000 | valeur);
  }

  /// The period as two parts: what it is ("October", "20 October", "19 – 25 Oct") and
  /// its year, which the title sets apart in the accent colour.
  (String, String) _titreDeLaPeriode(BuildContext context) {
    final langue = langueDesDates(context);
    final annee = DateFormat.y(langue).format(_ancre);
    switch (_vue) {
      case VueDAgenda.jour:
        return (DateFormat.MMMMd(langue).format(_ancre), annee);
      case VueDAgenda.semaine:
        final debut = debutDeSemaine(_ancre, _premierJour);
        final fin = plusJours(debut, 6);
        return (
          '${DateFormat.MMMd(langue).format(debut)} – ${DateFormat.MMMd(langue).format(fin)}',
          DateFormat.y(langue).format(fin),
        );
      case VueDAgenda.mois:
      case VueDAgenda.liste:
        // "octobre" heads the screen: a title takes its capital in French too.
        return (
          toBeginningOfSentenceCase(DateFormat.MMMM(langue).format(_ancre)),
          annee,
        );
    }
  }

  Widget _titre(BuildContext context) {
    final gc = Gc.of(context);
    final (periode, annee) = _titreDeLaPeriode(context);
    return Text.rich(
      key: const Key('agenda.titre'),
      TextSpan(
        children: [
          TextSpan(
            text: periode,
            style: TextStyle(color: gc.encre),
          ),
          TextSpan(
            text: ' $annee',
            style: TextStyle(color: gc.accentTexte),
          ),
        ],
      ),
      maxLines: 1,
      style: const TextStyle(
        fontSize: 30,
        fontWeight: FontWeight.w800,
        letterSpacing: -0.5,
      ),
    );
  }

  List<Calendrier> get _inscriptibles =>
      _calendriers.where((c) => c.inscriptible).toList();

  Future<void> _nouvelEvenement({DateTime? debut}) async {
    final cree = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => EcranDeNouvelEvenement(
          session: widget.session,
          calendriers: _inscriptibles,
          jour: debut ?? _ancre,
          debut: debut,
        ),
      ),
    );
    if (cree == true) await _recharger();
  }

  Future<void> _ouvrir(LigneDAgenda ligne) async {
    // A series occurrence, a booking or an external busy slot has no event id: it is
    // shown, not edited. A sheet says what it is instead of a tap that does nothing.
    if (ligne.evenement == null) {
      final gc = Gc.of(context);
      final (titre, style) = titreAffiche(context, ligne, gc);
      await showModalBottomSheet<void>(
        context: context,
        builder: (_) => SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  titre,
                  style: style.copyWith(
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  _horaire(context, ligne),
                  style: TextStyle(color: gc.estompe),
                ),
                if (ligne.lieu != null)
                  Text(ligne.lieu!, style: TextStyle(color: gc.estompe)),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Icon(Icons.lock_outline, size: 16, color: gc.estompe),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        L.of(context).lectureSeule,
                        style: TextStyle(color: gc.estompe, fontSize: 12),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      );
      return;
    }
    final modifie = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => EcranDeNouvelEvenement(
          session: widget.session,
          calendriers: _inscriptibles,
          jour: ligne.debut,
          evenement: ligne.evenement,
        ),
      ),
    );
    if (modifie == true) await _recharger();
  }

  String _horaire(BuildContext context, LigneDAgenda ligne) =>
      ligne.journeeEntiere
      ? L.of(context).journee
      : '${heureCourte(context, ligne.debut)} – ${heureCourte(context, ligne.fin)}';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        toolbarHeight: 68,
        centerTitle: false,
        titleSpacing: Mesures.marge,
        // Scaled down rather than cut: a truncated year is wrong information, not a
        // cosmetic issue (seen on the first App Store capture).
        title: FittedBox(
          fit: BoxFit.scaleDown,
          alignment: Alignment.centerLeft,
          child: _titre(context),
        ),
        actions: [
          // Only when auto-lock waits: with "immediately", leaving the app already locks.
          // `ListenableBuilder` because the setting is changed in another tab.
          ListenableBuilder(
            listenable: widget.verrouillage,
            builder: (_, _) => widget.verrouillage.cadenasVisible
                ? IconButton(
                    icon: const Icon(Icons.lock_outline),
                    tooltip: L.of(context).verrouillerLeCoffre,
                    onPressed: widget.session.verrouiller,
                  )
                : const SizedBox.shrink(),
          ),
          IconButton(
            icon: const Icon(Icons.chevron_left),
            tooltip: L.of(context).periodePrecedente,
            onPressed: () => _deplacer(-1),
          ),
          IconButton(
            icon: const Icon(Icons.today),
            tooltip: L.of(context).aujourdHui,
            onPressed: () => _allerA(DateTime.now()),
          ),
          IconButton(
            icon: const Icon(Icons.chevron_right),
            tooltip: L.of(context).periodeSuivante,
            onPressed: () => _deplacer(1),
          ),
        ],
      ),
      // Only with a calendar to write to: a shared calendar may be read-only, and
      // offering to write there would fail after everything was typed.
      floatingActionButton: _inscriptibles.isEmpty
          ? null
          : FloatingActionButton(
              // All tabs live in an IndexedStack: every floating button needs its own
              // hero tag, or Flutter throws "multiple heroes share the same tag".
              heroTag: 'agenda',
              tooltip: L.of(context).nouvelEvenement,
              onPressed: () => _nouvelEvenement(),
              child: const Icon(Icons.add),
            ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 4),
            child: SizedBox(
              width: double.infinity,
              child: SegmentedButton<VueDAgenda>(
                key: const Key('agenda.vues'),
                showSelectedIcon: false,
                style: const ButtonStyle(visualDensity: VisualDensity.compact),
                segments: [
                  for (final vue in VueDAgenda.values)
                    ButtonSegment(
                      value: vue,
                      label: Text(vue.libelle(L.of(context))),
                    ),
                ],
                selected: {_vue},
                onSelectionChanged: (choix) =>
                    _allerA(_ancre, vue: choix.first),
              ),
            ),
          ),
          if (_charge)
            const LinearProgressIndicator(minHeight: 2)
          else
            const SizedBox(height: 2),
          if (_erreur != null)
            Padding(
              padding: const EdgeInsets.all(12),
              child: Text(
                _erreur!,
                style: TextStyle(color: Gc.of(context).danger),
              ),
            ),
          Expanded(
            // Swipe left or right to move by one period, like every calendar app.
            child: GestureDetector(
              onHorizontalDragEnd: (details) {
                final vitesse = details.primaryVelocity ?? 0;
                if (vitesse.abs() < 300) return;
                _deplacer(vitesse < 0 ? 1 : -1);
              },
              child: _corps(context),
            ),
          ),
        ],
      ),
    );
  }

  Widget _corps(BuildContext context) {
    final lignes = _lignes;
    if (lignes == null) {
      return _erreur == null
          ? const Center(child: CircularProgressIndicator())
          : const SizedBox();
    }
    switch (_vue) {
      case VueDAgenda.jour:
        final semaine = debutDeSemaine(_ancre, _premierJour);
        return Column(
          children: [
            BandeauDeSemaine(
              jours: [for (var i = 0; i < 7; i++) plusJours(semaine, i)],
              selection: _ancre,
              lignes: lignes,
              couleurDe: _couleurDe,
              surJour: _allerA,
            ),
            Expanded(
              child: GrilleHoraire(
                key: ValueKey('jour-$_ancre'),
                jours: [_ancre],
                lignes: lignes,
                couleurDe: _couleurDe,
                surLigne: _ouvrir,
                surCreneau: _inscriptibles.isEmpty
                    ? null
                    : (d) => _nouvelEvenement(debut: d),
              ),
            ),
          ],
        );
      case VueDAgenda.semaine:
        final debut = debutDeSemaine(_ancre, _premierJour);
        return GrilleHoraire(
          key: ValueKey('semaine-$debut'),
          jours: [for (var i = 0; i < 7; i++) plusJours(debut, i)],
          lignes: lignes,
          couleurDe: _couleurDe,
          surLigne: _ouvrir,
          surCreneau: _inscriptibles.isEmpty
              ? null
              : (d) => _nouvelEvenement(debut: d),
          surJour: (jour) => _allerA(jour, vue: VueDAgenda.jour),
        );
      case VueDAgenda.mois:
        // Tapping the selected day again opens it, as in Fantastical.
        void surJour(DateTime jour) => memeJour(jour, _ancre)
            ? _allerA(jour, vue: VueDAgenda.jour)
            : (jour.month == _ancre.month
                  ? setState(() => _ancre = minuit(jour))
                  : _allerA(jour));
        return LayoutBuilder(
          builder: (context, contraintes) {
            // ─── Une seule mesure, deux décisions ───
            //
            // Les cases assez grandes portent les titres ; la liste du jour, en dessous,
            // ne dit alors plus rien que la grille ne dise déjà — on la retire. Les deux
            // décisions viennent du **même** appel : séparées, elles finiraient par se
            // contredire, et on aurait soit les titres deux fois, soit un mois muet
            // au-dessus d'une liste.
            final titres = titresParCaseDuMois(contraintes.biggest);
            final grille = GrilleDuMois(
              mois: _ancre,
              jours: joursDeLaGrilleDuMois(_ancre, _premierJour),
              selection: _ancre,
              lignes: lignes,
              couleurDe: _couleurDe,
              titresParCase: titres,
              surJour: surJour,
            );
            if (titres > 0) return grille;
            // Sans titres, la grille garde la hauteur d'un téléphone et cède le reste à la
            // liste : étirée, elle donnerait six rangées hautes et vides.
            // The list runs from the selected day to the end of the loaded grid: past it
            // nothing was fetched, and an empty day there would be a lie.
            final finDeLaGrille = joursDeLaGrilleDuMois(
              _ancre,
              _premierJour,
            ).last;
            final restants = finDeLaGrille.difference(_ancre).inDays + 1;
            return Column(
              children: [
                SizedBox(height: _hauteurDeLaGrilleEnPastilles, child: grille),
                Divider(height: 1, color: Gc.of(context).bordureFranche),
                Expanded(
                  child: ListeParJour(
                    key: ValueKey(('month-list', _ancre)),
                    debut: _ancre,
                    jours: restants.clamp(1, _joursSousLeMois),
                    lignes: lignes,
                    taches: _taches,
                    couleurDe: _couleurDe,
                    surLigne: _ouvrir,
                    surTache: _cocher,
                  ),
                ),
              ],
            );
          },
        );
      case VueDAgenda.liste:
        return RefreshIndicator(
          onRefresh: _recharger,
          child: ListeParJour(
            debut: _ancre,
            jours: _joursDeLaListe,
            lignes: lignes,
            taches: _taches,
            couleurDe: _couleurDe,
            surLigne: _ouvrir,
            surTache: _cocher,
          ),
        );
    }
  }
}
