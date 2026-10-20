import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/session.dart';
import '../services/apparence.dart';
import '../services/rappels.dart';
import '../services/vue_agenda.dart';
import '../services/verrouillage.dart';
import '../theme.dart';
import 'agenda.dart';
import 'reglages.dart';
import 'reunions.dart';
import 'types_de_rendez_vous.dart';
import 'taches.dart';
import '../l10n/generated/app_localisations.dart';

/// L'application une fois le coffre ouvert.
///
/// Un onglet par fonction **qui existe**. Le client natif en a cinq ; en afficher cinq ici,
/// dont certains vides, laisserait croire à un chargement perpétuel plutôt qu'à un portage
/// en cours. Chacun s'ajoute quand son écran est écrit, pas avant.
class EcranDAccueil extends StatefulWidget {
  const EcranDAccueil({
    super.key,
    required this.session,
    required this.verrouillage,
    this.apparence,
    this.rappels,
  });

  final Session session;
  final Verrouillage verrouillage;
  final Apparence? apparence;
  final Rappels? rappels;

  @override
  State<EcranDAccueil> createState() => _EcranDAccueilState();
}

class _EcranDAccueilState extends State<EcranDAccueil>
    with WidgetsBindingObserver {
  int _onglet = 0;
  DateTime? _partiEnArrierePlan;
  final _agenda = GlobalKey<EcranDAgendaState>();

  /// The macOS menu bar's "Settings…" (⌘,) arrives here; the native side sends
  /// `reglages`. Nothing sends it elsewhere.
  static const _canalDuMenu = MethodChannel('ch.stackops.ghostcal/menu');

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _replanifierLesRappels();
    _canalDuMenu.setMethodCallHandler((appel) async {
      if (appel.method == 'reglages' && mounted) setState(() => _onglet = 4);
    });
  }

  /// A booking taken while the app was away gets its reminder as soon as it is back,
  /// without waiting for the background refresh.
  void _replanifierLesRappels() {
    final rappels = widget.rappels;
    final api = widget.session.api;
    if (rappels == null || api == null) return;
    unawaited(
      rappels
          .replanifier(api, organisation: widget.session.organisation)
          .catchError(
            (Object e) => debugPrint('ghostcal.rappels: refresh failed: $e'),
          ),
    );
  }

  @override
  void dispose() {
    _canalDuMenu.setMethodCallHandler(null);
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  /// Un coffre qui reste ouvert pendant que le téléphone circule n'est plus un coffre.
  ///
  /// On note **quand** on est parti, et on décide au retour : mesurer à l'aller
  /// obligerait à tenir une minuterie que le système peut suspendre sans prévenir.
  @override
  void didChangeAppLifecycleState(AppLifecycleState etat) {
    if (etat == AppLifecycleState.resumed) {
      _replanifierLesRappels();
      final parti = _partiEnArrierePlan;
      _partiEnArrierePlan = null;
      if (parti != null &&
          widget.verrouillage.doitVerrouiller(
            depuis: parti,
            maintenant: DateTime.now(),
          )) {
        widget.session.verrouiller();
      }
    } else if (etat == AppLifecycleState.paused ||
        etat == AppLifecycleState.hidden) {
      _partiEnArrierePlan ??= DateTime.now();
    }
  }

  @override
  Widget build(BuildContext context) {
    return FondGhost(
      child: Scaffold(
        // The signal that the vault is open and the app is ready, for the integration
        // tests: it used to be the tab bar, which the floating bar replaced.
        key: const Key('accueil.pret'),
        // `ContenuBorne` ici et pas autour du `Scaffold` : la barre du bas doit garder
        // toute la largeur.
        //
        // Une borne **par section** et non une seule autour de la pile, depuis qu'il existe
        // des fenêtres larges : l'agenda veut de la largeur là où les quatre autres n'en
        // veulent pas. Une liste de tâches sur 1100 points donne des lignes qu'on lit de
        // gauche à droite en tournant la tête ; une semaine sur 560 donne sept colonnes de
        // 72 points. Les deux besoins sont contraires, et une borne unique en trahit un.
        body: IndexedStack(
          index: _onglet,
          children: [
            ContenuBorne(
              largeur: Mesures.largeurDeLAgenda,
              child: EcranDAgenda(
                key: _agenda,
                session: widget.session,
                verrouillage: widget.verrouillage,
                surChangement: () {
                  if (mounted) setState(() {});
                },
              ),
            ),
            ContenuBorne(child: EcranDeTaches(session: widget.session)),
            ContenuBorne(child: EcranDeReunions(session: widget.session)),
            ContenuBorne(
              child: EcranDeTypesDeRendezVous(session: widget.session),
            ),
            ContenuBorne(
              child: EcranDeReglages(
                session: widget.session,
                verrouillage: widget.verrouillage,
                apparence: widget.apparence,
                rappels: widget.rappels,
              ),
            ),
          ],
        ),
        bottomNavigationBar: _barre(context),
      ),
    );
  }

  /// Fantastical's bottom bar: a round menu button, a pill that filters the calendars
  /// (or leads back to the agenda from another section), and search with "new".
  Widget _barre(BuildContext context) {
    final l = L.of(context);
    final agenda = _agenda.currentState;
    final surLAgenda = _onglet == 0;
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Mesures.marge, 6, Mesures.marge, 10),
        child: Row(
          children: [
            _Flottant(
              child: IconButton(
                key: const Key('accueil.menu'),
                tooltip: l.menu,
                icon: const Icon(Icons.menu),
                onPressed: _ouvrirLeMenu,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _Flottant(
                child: InkWell(
                  key: const Key('accueil.calendriers'),
                  customBorder: const StadiumBorder(),
                  onTap: surLAgenda
                      ? _choisirLesCalendriers
                      : () => setState(() => _onglet = 0),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 18),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        if (!surLAgenda) ...[
                          const Icon(Icons.chevron_left, size: 20),
                          const SizedBox(width: 4),
                        ],
                        Flexible(
                          child: Text(
                            surLAgenda
                                ? _libelleDesCalendriers(l)
                                : l.ongletAgenda,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
            if (surLAgenda) ...[
              const SizedBox(width: 10),
              _Flottant(
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    IconButton(
                      key: const Key('accueil.rechercher'),
                      tooltip: l.rechercher,
                      icon: const Icon(Icons.search),
                      onPressed: () => agenda?.rechercher(),
                    ),
                    // Only with a calendar to write to: a shared calendar may be
                    // read-only, and offering to write there would fail after
                    // everything was typed.
                    if (agenda?.peutCreer ?? false)
                      IconButton(
                        key: const Key('accueil.nouveau'),
                        tooltip: l.nouvelEvenement,
                        icon: const Icon(Icons.add),
                        onPressed: () => agenda?.nouvelEvenement(),
                      ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  String _libelleDesCalendriers(L l) {
    final agenda = _agenda.currentState;
    if (agenda == null || agenda.masques.isEmpty) return l.tousLesCalendriers;
    final visibles = agenda.calendriers
        .where((c) => !agenda.masques.contains(c.id))
        .toList();
    return visibles.length == 1
        ? visibles.single.nom
        : l.calendriersAffiches(visibles.length);
  }

  /// The menu: the agenda's views, then the other sections. Choosing a view also
  /// brings the agenda back.
  Future<void> _ouvrirLeMenu() async {
    final l = L.of(context);
    final vue = _agenda.currentState?.vue;
    final choix = await showModalBottomSheet<Object>(
      context: context,
      showDragHandle: true,
      // Its own height, not the default nine-sixteenths of the screen: Settings, the
      // last entry, was cut off on a phone.
      isScrollControlled: true,
      builder: (context) {
        Widget entree(
          Object valeur,
          IconData icone,
          String libelle,
          bool courant,
        ) => ListTile(
          visualDensity: VisualDensity.compact,
          leading: Icon(icone),
          title: Text(libelle),
          trailing: courant ? const Icon(Icons.check) : null,
          onTap: () => Navigator.of(context).pop(valeur),
        );
        return SafeArea(
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (final (v, icone) in [
                  (VueDAgenda.jour, Icons.crop_portrait),
                  (VueDAgenda.semaine, Icons.view_week_outlined),
                  (VueDAgenda.mois, Icons.calendar_view_month),
                  (VueDAgenda.liste, Icons.view_agenda_outlined),
                ])
                  entree(v, icone, v.libelle(l), _onglet == 0 && vue == v),
                const Divider(),
                entree(
                  1,
                  Icons.check_box_outlined,
                  l.ongletTaches,
                  _onglet == 1,
                ),
                entree(
                  2,
                  Icons.groups_outlined,
                  l.ongletReunions,
                  _onglet == 2,
                ),
                entree(
                  3,
                  Icons.event_available_outlined,
                  l.ongletRdv,
                  _onglet == 3,
                ),
                entree(
                  4,
                  Icons.settings_outlined,
                  l.ongletReglages,
                  _onglet == 4,
                ),
              ],
            ),
          ),
        );
      },
    );
    if (!mounted || choix == null) return;
    if (choix is VueDAgenda) {
      setState(() => _onglet = 0);
      _agenda.currentState?.choisirLaVue(choix);
    } else if (choix is int) {
      setState(() => _onglet = choix);
    }
  }

  /// Which calendars the agenda shows. Bookings and busy slots from linked accounts
  /// have no calendar and are never hidden.
  Future<void> _choisirLesCalendriers() async {
    final agenda = _agenda.currentState;
    if (agenda == null) return;
    final l = L.of(context);
    var masques = {...agenda.masques};
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => StatefulBuilder(
        builder: (context, majour) {
          void poser(Set<String> valeur) {
            majour(() => masques = valeur);
            agenda.masquer(valeur);
          }

          return SafeArea(
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(
                      Mesures.marge,
                      0,
                      Mesures.marge,
                      8,
                    ),
                    child: Text(
                      l.calendriersAAfficher,
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  CheckboxListTile(
                    key: const Key('calendriers.tous'),
                    title: Text(l.tousLesCalendriers),
                    value: masques.isEmpty,
                    onChanged: (_) => poser(const {}),
                  ),
                  const Divider(),
                  for (final c in agenda.calendriers)
                    CheckboxListTile(
                      key: Key('calendriers.${c.id}'),
                      secondary: CircleAvatar(
                        radius: 7,
                        backgroundColor: _couleur(c.couleur),
                      ),
                      title: Text(c.nom),
                      value: !masques.contains(c.id),
                      onChanged: (montre) => poser(
                        montre == true
                            ? ({...masques}..remove(c.id))
                            : {...masques, c.id},
                      ),
                    ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Color _couleur(String hex) {
    final valeur = int.tryParse(hex.replaceFirst('#', ''), radix: 16);
    return valeur == null ? Gc.of(context).accent : Color(0xFF000000 | valeur);
  }
}

/// A floating rounded surface, the material of the bottom bar.
class _Flottant extends StatelessWidget {
  const _Flottant({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    return Material(
      color: gc.surface.withValues(alpha: gc.sombre ? 0.94 : 0.97),
      shape: StadiumBorder(side: BorderSide(color: gc.bordure)),
      elevation: 4,
      shadowColor: Colors.black.withValues(alpha: 0.25),
      clipBehavior: Clip.antiAlias,
      child: SizedBox(height: 52, child: Center(widthFactor: 1, child: child)),
    );
  }
}
