import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../l10n/generated/app_localisations.dart';
import '../outils/calendrier.dart';
import '../outils/dates.dart';
import '../services/agenda.dart';
import '../services/erreurs.dart';
import '../services/session.dart';
import '../services/taches.dart';
import '../services/trousseau.dart';
import '../services/verrouillage.dart';
import '../services/vue_agenda.dart';
import '../theme.dart';
import 'agenda_jours.dart';
import 'agenda_vues.dart';
import 'nouvel_evenement.dart';
import 'recherche.dart';

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
    this.surChangement,
  });

  final Session session;
  final Verrouillage verrouillage;

  /// Called when what the bottom bar shows of the agenda changes: the view, the
  /// calendars shown, whether an event can be created.
  final VoidCallback? surChangement;

  @override
  State<EcranDAgenda> createState() => EcranDAgendaState();
}

/// How the month is drawn. `automatique` lets the space decide
/// ([titresParCaseDuMois]); the two others are the user's override, set with the
/// handle under the grid, and each points away from what the space would give.
enum ModeDuMois { automatique, compact, titres }

/// Public so that the home screen's bottom bar can drive the agenda: pick the view,
/// filter the calendars, search, create.
class EcranDAgendaState extends State<EcranDAgenda> {
  static const _cleDesMasques = 'ghostcal.agenda.calendriers-masques';
  static const _cleDuMois = 'ghostcal.agenda.mois';

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

  /// Calendars the user chose not to see. Bookings and external busy slots have no
  /// calendar and always show: hiding them would hide a commitment.
  Set<String> _masques = const {};
  ModeDuMois _modeDuMois = ModeDuMois.automatique;

  /// Ce que le panneau d'inspection montre, sur les fenêtres larges.
  ///
  /// `null` quand il n'y a rien à montrer — le panneau disparaît alors et la grille
  /// reprend toute la place. Sur un téléphone il reste toujours `null` : l'écran y est
  /// poussé par-dessus, comme avant.
  ({String? evenement, DateTime jour, DateTime? debut, DateTime? occurrence})?
  _inspecte;

  @override
  void initState() {
    super.initState();
    VueDAgenda.retenue().then((vue) {
      if (!mounted) return;
      setState(() => _vue = vue);
      _recharger();
      widget.surChangement?.call();
    });
    _lireLesPreferences();
  }

  Future<void> _lireLesPreferences() async {
    try {
      final masques = await Trousseau.lire(_cleDesMasques);
      final mois = await Trousseau.lire(_cleDuMois);
      if (!mounted) return;
      setState(() {
        _masques = {...?masques?.split(',').where((x) => x.isNotEmpty)};
        _modeDuMois = ModeDuMois.values.firstWhere(
          (m) => m.name == mois,
          orElse: () => ModeDuMois.automatique,
        );
      });
      widget.surChangement?.call();
    } on Object catch (e) {
      debugPrint('ghostcal.agenda: preferences not read: $e');
    }
  }

  Future<void> _retenir(String valeur, String cle) async {
    try {
      await Trousseau.poser(valeur, cle);
    } on Object catch (e) {
      debugPrint('ghostcal.agenda: preference not saved: $e');
    }
  }

  // ─── What the bottom bar reads and drives ───

  VueDAgenda get vue => _vue;

  /// Le jour autour duquel la vue est construite. Lu par les témoins : « Aujourd'hui »
  /// et les deux flèches ne changent **que** cela, et ne se constatent donc nulle part
  /// ailleurs sans relire un titre mis en forme.
  DateTime get ancre => _ancre;
  bool get peutCreer => _inscriptibles.isNotEmpty;
  List<Calendrier> get calendriers => _calendriers;
  Set<String> get masques => _masques;

  void choisirLaVue(VueDAgenda vue) => _allerA(_ancre, vue: vue);
  Future<void> nouvelEvenement() => _nouvelEvenement();

  /// The macOS menu bar drives these two. `_allerA` and `_deplacer` stay private:
  /// they take an anchor and a sign that only this screen knows how to form.
  void allerAujourdhui() => _allerA(DateTime.now());

  /// Le mini-mois de la colonne latérale saute à n'importe quel jour — là où les
  /// chevrons de l'en-tête coûtent un clic par période franchie.
  void allerAuJour(DateTime jour) => _allerA(jour);
  void deplacer(int sens) => _deplacer(sens);

  Future<void> masquer(Set<String> masques) async {
    setState(() => _masques = masques);
    widget.surChangement?.call();
    await _retenir(masques.join(','), _cleDesMasques);
  }

  Future<void> rechercher() async {
    final agenda = _agenda;
    final organisation = widget.session.organisation;
    if (agenda == null || organisation == null) return;
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => EcranDeRecherche(
          agenda: agenda,
          organisation: organisation,
          couleurDe: _couleurDe,
          surLigne: _ouvrir,
          visible: _visible,
        ),
      ),
    );
  }

  /// Le même seuil que la chrome de l'accueil, et pour la même raison : c'est la place
  /// qui décide, pas la plateforme. En dessous, un panneau de 340 points laisserait à la
  /// grille de quoi afficher trois colonnes.
  bool get _bureau => MediaQuery.sizeOf(context).width >= Mesures.seuilBureau;

  bool _visible(LigneDAgenda ligne) =>
      ligne.calendrier == null || !_masques.contains(ligne.calendrier);

  /// The month's mode flipped from what is on screen: the handle always shows the
  /// other way of reading the month.
  void _basculerLeMois(bool titresAffiches) {
    final mode = titresAffiches ? ModeDuMois.compact : ModeDuMois.titres;
    setState(() => _modeDuMois = mode);
    _retenir(mode.name, _cleDuMois);
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
      if (_calendriers.isEmpty) {
        _calendriers = await agenda.calendriers();
        widget.surChangement?.call();
      }
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
    if (vue != null) {
      vue.retenir();
      widget.surChangement?.call();
    }
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
    if (_bureau) {
      setState(
        () => _inspecte = (
          evenement: null,
          jour: debut ?? _ancre,
          debut: debut,
          occurrence: null,
        ),
      );
      return;
    }
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
    if (_bureau) {
      setState(
        () => _inspecte = (
          evenement: ligne.evenement,
          jour: ligne.debut,
          debut: null,
          occurrence: ligne.debut,
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
          occurrence: ligne.debut,
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
      body: Column(
        children: [
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
              child: _avecPanneau(context, _corps(context)),
            ),
          ),
        ],
      ),
    );
  }

  /// La grille et, à côté d'elle, l'événement — au lieu de l'écran poussé par-dessus.
  ///
  /// C'est ce qui distingue un agenda de bureau d'un agenda de téléphone : on garde sous
  /// les yeux ce qu'on est en train de regarder. Cliquer un rendez-vous pour vérifier son
  /// heure ne doit pas faire disparaître la semaine dont on le compare.
  ///
  /// L'écran logé ici est **le même** que celui qu'on pousse ailleurs : deux écrans
  /// jumeaux divergeraient à la première correction faite d'un seul côté. Il ne sait
  /// qu'une chose de plus — comment se refermer sans route, par `surFin`.
  Widget _avecPanneau(BuildContext context, Widget grille) {
    final inspecte = _inspecte;
    if (inspecte == null || !_bureau) return grille;
    return Row(
      children: [
        Expanded(child: grille),
        VerticalDivider(width: 1, color: Gc.of(context).bordure),
        SizedBox(
          width: 360,
          child: EcranDeNouvelEvenement(
            // La clé force un écran neuf quand on passe d'un événement à un autre :
            // sans elle, Flutter réutiliserait l'état, et les champs garderaient le
            // titre du précédent.
            key: ValueKey(('inspection', inspecte.evenement, inspecte.jour)),
            session: widget.session,
            calendriers: _inscriptibles,
            jour: inspecte.jour,
            evenement: inspecte.evenement,
            debut: inspecte.debut,
            occurrence: inspecte.occurrence,
            surFin: (modifie) {
              setState(() => _inspecte = null);
              if (modifie) unawaited(_recharger());
            },
          ),
        ),
      ],
    );
  }

  Widget _corps(BuildContext context) {
    final lignes = _lignes?.where(_visible).toList();
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
                taches: _taches,
                surTache: _cocher,
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
          taches: _taches,
          surTache: _cocher,
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
            final selonLaPlace = titresParCaseDuMois(contraintes.biggest);
            // The handle overrides the space, at this one place: compact always gives
            // dots and the day list, titles always give titles — on a phone they are
            // cut short, as in Fantastical's expanded month, and still say which day is
            // busy with what.
            // ─── Sur le bureau, la place décide seule ───
            //
            // La poignée qui bascule pastilles/titres est un geste de pouce, et elle
            // disparaît au-dessus du seuil. Son réglage doit donc disparaître avec
            // elle : sinon un « compact » mémorisé sur un téléphone suivrait la
            // personne jusqu'au Mac, où plus rien ne permettrait d'en sortir. C'est
            // arrivé — un mois muet sur 1440 points, et le code accusé à tort.
            final bureau = contraintes.maxWidth >= Mesures.seuilBureau;
            final titres = bureau
                ? selonLaPlace
                : switch (_modeDuMois) {
                    ModeDuMois.automatique => selonLaPlace,
                    ModeDuMois.compact => 0,
                    ModeDuMois.titres => selonLaPlace > 0 ? selonLaPlace : 1,
                  };
            final grille = GrilleDuMois(
              mois: _ancre,
              jours: joursDeLaGrilleDuMois(_ancre, _premierJour),
              selection: _ancre,
              lignes: lignes,
              couleurDe: _couleurDe,
              titresParCase: titres,
              surJour: surJour,
            );
            if (titres > 0) {
              if (bureau) return grille;
              return Column(
                children: [
                  Expanded(child: grille),
                  _Poignee(
                    ouverte: true,
                    surBascule: () => _basculerLeMois(true),
                  ),
                ],
              );
            }
            final poignee = _Poignee(
              ouverte: false,
              surBascule: () => _basculerLeMois(false),
            );
            // Sans titres, la grille garde la hauteur d'un téléphone et cède le reste à la
            // liste : étirée, elle donnerait six rangées hautes et vides.
            // The list runs from the selected day to the end of the loaded grid: past it
            // nothing was fetched, and an empty day there would be a lie.
            final finDeLaGrille = joursDeLaGrilleDuMois(
              _ancre,
              _premierJour,
            ).last;
            final restants = finDeLaGrille.difference(_ancre).inDays + 1;
            final liste = ListeParJour(
              key: ValueKey(('month-list', _ancre)),
              debut: _ancre,
              jours: restants.clamp(1, _joursSousLeMois),
              lignes: lignes,
              taches: _taches,
              couleurDe: _couleurDe,
              surLigne: _ouvrir,
              surTache: _cocher,
            );
            final bordure = Gc.of(context).bordureFranche;
            // Too short for the grid above a list — a phone held sideways: the grid takes
            // the left and the list the right, as on a tablet, rather than the grid
            // running under the tab bar.
            if (contraintes.maxHeight < _hauteurDeLaGrilleEnPastilles + 160) {
              return Row(
                children: [
                  Expanded(
                    flex: 3,
                    child: Column(
                      children: [
                        Expanded(child: grille),
                        poignee,
                      ],
                    ),
                  ),
                  VerticalDivider(width: 1, color: bordure),
                  Expanded(flex: 2, child: liste),
                ],
              );
            }
            return Column(
              children: [
                SizedBox(height: _hauteurDeLaGrilleEnPastilles, child: grille),
                poignee,
                Divider(height: 1, color: bordure),
                Expanded(child: liste),
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

/// The bar under the month that flips it between dots-and-list and titles in the cells:
/// tap it, or drag it down to open the month and up to close it.
class _Poignee extends StatelessWidget {
  const _Poignee({required this.ouverte, required this.surBascule});

  /// Whether the month shows titles now.
  final bool ouverte;
  final VoidCallback surBascule;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final l = L.of(context);
    return Semantics(
      button: true,
      label: ouverte ? l.reduireLeMois : l.developperLeMois,
      child: GestureDetector(
        key: const Key('agenda.poignee'),
        behavior: HitTestBehavior.opaque,
        onTap: surBascule,
        onVerticalDragEnd: (details) {
          final vitesse = details.primaryVelocity ?? 0;
          if (ouverte ? vitesse < -150 : vitesse > 150) surBascule();
        },
        child: SizedBox(
          height: 20,
          width: double.infinity,
          child: Center(
            child: Container(
              width: 40,
              height: 5,
              decoration: BoxDecoration(
                color: gc.estompe.withValues(alpha: 0.5),
                borderRadius: BorderRadius.circular(3),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
