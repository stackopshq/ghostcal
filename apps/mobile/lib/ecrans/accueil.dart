import 'dart:async';

import 'package:flutter/foundation.dart';
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

  /// The macOS menu bar. The native side names the methods; see
  /// `macos/Runner/MenuDeLApplication.swift`.
  static const _canalDuMenu = MethodChannel('ch.stackops.ghostcal/menu');

  /// The search screen covers the agenda, so the menu stops reaching it — see
  /// [_recevoirDuMenu].
  bool _rechercheOuverte = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _replanifierLesRappels();
    _canalDuMenu.setMethodCallHandler(_recevoirDuMenu);
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

  /// Ce qu'un raccourci de la barre de menus déclenche.
  ///
  /// Les noms de méthode viennent du natif : `macos/Runner/MenuDeLApplication.swift`.
  /// Les deux listes doivent coïncider, et `test/menu_macos_test.dart` échoue si
  /// l'une des deux prend de l'avance — un item de menu dont la méthode n'arrive
  /// nulle part est un raccourci qui ne fait rien, en silence.
  ///
  /// Hormis « Réglages… » et « Verrouiller », ces commandes pilotent l'agenda et le
  /// ramènent donc d'abord devant : choisir « Mois » alors que les réglages occupent
  /// l'écran changerait une vue que personne ne regarde. La feuille de menu du bas
  /// fait déjà exactement cela.
  ///
  /// Et tant que l'écran de recherche est au premier plan, il couvre l'agenda :
  /// seul « Verrouiller » passe encore. ⌘F en particulier doit laisser une requête à
  /// moitié tapée tranquille plutôt que d'empiler une seconde recherche par-dessus.
  Future<void> _recevoirDuMenu(MethodCall appel) async {
    if (!mounted) return;

    // Avant la garde, et avant tout le reste : verrouiller est une commande de
    // sécurité. Elle doit aboutir quel que soit l'écran au premier plan — refuser de
    // fermer le coffre parce qu'une recherche est ouverte serait le mauvais arbitrage.
    if (appel.method == 'verrouiller') {
      widget.session.verrouiller();
      return;
    }
    if (_rechercheOuverte) return;
    final agenda = _agenda.currentState;

    void surLAgenda(void Function(EcranDAgendaState agenda) faire) {
      if (agenda == null) return;
      setState(() => _onglet = 0);
      faire(agenda);
    }

    switch (appel.method) {
      case 'reglages':
        setState(() => _onglet = 4);
      case 'vue':
        final vue = switch (appel.arguments) {
          'jour' => VueDAgenda.jour,
          'semaine' => VueDAgenda.semaine,
          'mois' => VueDAgenda.mois,
          'liste' => VueDAgenda.liste,
          _ => null,
        };
        if (vue != null) surLAgenda((a) => a.choisirLaVue(vue));
      case 'aujourdhui':
        surLAgenda((a) => a.allerAujourdhui());
      case 'precedent':
        surLAgenda((a) => a.deplacer(-1));
      case 'suivant':
        surLAgenda((a) => a.deplacer(1));
      case 'nouveau':
        // Le bouton de la barre disparaît sans calendrier inscriptible ; le
        // raccourci suit la même règle, plutôt que d'ouvrir un formulaire qui ne
        // pourra pas être enregistré.
        if (agenda != null && agenda.peutCreer) {
          surLAgenda((a) => a.nouvelEvenement());
        }
      case 'rechercher':
        if (agenda == null) return;
        setState(() => _onglet = 0);
        _rechercheOuverte = true;
        try {
          await agenda.rechercher();
        } finally {
          _rechercheOuverte = false;
        }
    }
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

  /// Fantastical's shortcuts on any keyboard: ⌘1–⌘4 for the views, ⌘T for today,
  /// ⌘← ⌘→ to page, ⌘N for a new event, ⌘F to search, ⌘, for the settings, ⌘L to
  /// lock. Command on Apple keyboards, Control elsewhere — an Android tablet or a
  /// desktop with a keyboard gets them too.
  ///
  /// Each key sends the menu bar's command to [_recevoirDuMenu], so a key and its menu
  /// item share one path and one set of guards. On macOS AppKit answers the key first
  /// through the menu item, and this map never sees it.
  Map<ShortcutActivator, VoidCallback> get _raccourcis {
    final pomme = switch (defaultTargetPlatform) {
      TargetPlatform.macOS || TargetPlatform.iOS => true,
      _ => false,
    };
    SingleActivator touche(LogicalKeyboardKey cle) =>
        SingleActivator(cle, meta: pomme, control: !pomme);
    VoidCallback commande(String methode, [Object? argument]) =>
        () => unawaited(_recevoirDuMenu(MethodCall(methode, argument)));
    return {
      touche(LogicalKeyboardKey.digit1): commande('vue', 'jour'),
      touche(LogicalKeyboardKey.digit2): commande('vue', 'semaine'),
      touche(LogicalKeyboardKey.digit3): commande('vue', 'mois'),
      touche(LogicalKeyboardKey.digit4): commande('vue', 'liste'),
      touche(LogicalKeyboardKey.keyT): commande('aujourdhui'),
      touche(LogicalKeyboardKey.arrowLeft): commande('precedent'),
      touche(LogicalKeyboardKey.arrowRight): commande('suivant'),
      touche(LogicalKeyboardKey.keyN): commande('nouveau'),
      touche(LogicalKeyboardKey.keyF): commande('rechercher'),
      touche(LogicalKeyboardKey.comma): commande('reglages'),
      touche(LogicalKeyboardKey.keyL): commande('verrouiller'),
    };
  }

  @override
  Widget build(BuildContext context) {
    return CallbackShortcuts(
      bindings: _raccourcis,
      // Autofocus so the shortcuts work as soon as the vault opens, before anything
      // was clicked; a focused text field still gets its keys first.
      child: Focus(autofocus: true, child: _ecran(context)),
    );
  }

  Widget _ecran(BuildContext context) {
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
