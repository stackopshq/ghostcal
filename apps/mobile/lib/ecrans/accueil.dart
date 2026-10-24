import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/agenda.dart' show Calendrier;
import '../services/erreurs.dart' show lisible;
import '../services/session.dart';
import '../services/apparence.dart';
import '../services/rappels.dart';
import '../services/vue_agenda.dart';
import '../services/verrouillage.dart';
import '../theme.dart';
import '../services/abonnements.dart' show Abonnement;
import 'agenda.dart';
import 'ajouter_un_abonnement.dart';
import 'barre_de_titre.dart';
import 'colonne_laterale.dart';
import 'reglages.dart';
import 'renommer_un_calendrier.dart';
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
    // The digits by the key's position, not its character: on a French keyboard the
    // key above Q types "&", so ⌘1 by character never fired without Shift. AppKit
    // does this translation for the macOS menu; the map has to do it elsewhere.
    ShortcutActivator chiffre(PhysicalKeyboardKey cle) =>
        _ToucheParPosition(cle, meta: pomme, control: !pomme);
    VoidCallback commande(String methode, [Object? argument]) =>
        () => unawaited(_recevoirDuMenu(MethodCall(methode, argument)));
    return {
      chiffre(PhysicalKeyboardKey.digit1): commande('vue', 'jour'),
      chiffre(PhysicalKeyboardKey.digit2): commande('vue', 'semaine'),
      chiffre(PhysicalKeyboardKey.digit3): commande('vue', 'mois'),
      chiffre(PhysicalKeyboardKey.digit4): commande('vue', 'liste'),
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
    // ─── Deux chromes, une seule application ───
    //
    // Au-dessus de [Mesures.seuilBureau], les commandes montent dans la barre de titre
    // et la barre flottante du bas s'en va. En dessous, rien ne change : la barre
    // flottante est le bon outil pour un pouce, et elle reste la chrome d'Android,
    // d'iOS et d'une fenêtre qu'on a réduite.
    //
    // La bascule est une **mesure** et non une plateforme. Un iPad en paysage y gagne
    // autant qu'un Mac, et un Mac dont la fenêtre est étroite retrouve la barre du bas
    // plutôt qu'une barre d'outils tassée.
    final bureau = MediaQuery.sizeOf(context).width >= Mesures.seuilBureau;
    // L'accueil **dessine** dans la barre de titre : sa barre d'outils s'y tient, à
    // côté des pastilles de la fenêtre. Il rend donc la marge que l'application réserve
    // pour tous les écrans poussés — voir `_SousLaBarreDeTitre` dans `main.dart`. Sans
    // ce retrait, la barre d'outils descendrait de 52 points et laisserait la bande
    // vide, ce qui est exactement ce qu'on a enlevé.
    //
    // Seulement sur le bureau : en dessous du seuil il n'y a pas de barre d'outils, et
    // le contenu doit descendre sous les pastilles comme partout ailleurs.
    final ecran = FondGhost(
      child: Scaffold(
        appBar: bureau ? _barreDeTitre(context) : null,
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
        body: _corps(context, bureau: bureau),
        bottomNavigationBar: bureau ? null : _barre(context),
      ),
    );
    // ─── Deux questions, et elles ne se confondent pas ───
    //
    // `bureau` décide de la **chrome** : barre d'outils en haut, pas de barre flottante
    // en bas. La barre de titre traversée, elle, est une affaire de **plateforme** :
    // seul `MainFlutterWindow` fait passer la vue dessous, et seul macOS a des pastilles
    // à éviter.
    //
    // Les confondre retirait à l'iPad une encoche que personne ne lui avait ajoutée :
    // `_SousLaBarreDeTitre` ne pose ses 52 points que sur macOS, et ce retrait les
    // enlevait dès 900 points de large — donc sur un iPad dans les deux orientations.
    // L'`AppBar` se dessinait alors à y = 0, et l'heure, la batterie et le wifi se
    // posaient par-dessus la barre d'outils.
    //
    // Trouvé par la session iOS en lisant le code, avant que la build existe.
    final dansLaBarreDeTitre = Mesures.dansLaBarreDeTitre(
      bureau: bureau,
      plateforme: defaultTargetPlatform,
    );
    return dansLaBarreDeTitre
        ? MediaQuery.removePadding(
            context: context,
            removeTop: true,
            child: ecran,
          )
        : ecran;
  }

  /// Le corps, et la colonne qui l'accompagne sur les fenêtres larges.
  ///
  /// `IndexedStack` et non un `switch` : les cinq sections restent montées, donc
  /// l'agenda garde sa position et ses données quand on passe par les Réglages. C'est
  /// aussi ce qui permet à la colonne de lire l'état de l'agenda — `_agenda.currentState`
  /// ne vaut quelque chose que parce que l'écran n'est jamais démonté.
  Widget _corps(BuildContext context, {required bool bureau}) {
    final pile = IndexedStack(
      index: _onglet,
      children: [
        // ─── L'agenda n'est plus borné ───
        //
        // Il l'était à 1100 points, pour que la semaine garde des colonnes lisibles sur
        // un écran large. La colonne latérale a changé la donne : elle prend déjà 232
        // points, et sur un grand écran l'agenda se retrouvait en vignette centrée entre
        // deux marges vides — vu en capture sur 2000 points de large.
        //
        // Une grille de calendrier n'a pas de largeur « trop grande » : sept colonnes de
        // 280 points se lisent mieux que sept de 150, et c'est ce que montre tout agenda
        // de bureau. Les quatre autres sections gardent leur borne de 560 : une liste de
        // tâches sur 2000 points se lirait en tournant la tête.
        EcranDAgenda(
          key: _agenda,
          session: widget.session,
          verrouillage: widget.verrouillage,
          surChangement: () {
            if (mounted) setState(() {});
          },
        ),
        ContenuBorne(child: EcranDeTaches(session: widget.session)),
        ContenuBorne(child: EcranDeReunions(session: widget.session)),
        ContenuBorne(child: EcranDeTypesDeRendezVous(session: widget.session)),
        ContenuBorne(
          child: EcranDeReglages(
            session: widget.session,
            verrouillage: widget.verrouillage,
            apparence: widget.apparence,
            rappels: widget.rappels,
          ),
        ),
      ],
    );
    if (!bureau) return pile;
    // La colonne lit l'agenda plutôt que de tenir son propre état : deux sources pour
    // la même sélection finiraient par diverger, et c'est la colonne qui aurait tort.
    final agenda = _agenda.currentState;
    return Row(
      children: [
        ColonneLaterale(
          onglet: _onglet,
          surOnglet: (indice) => setState(() => _onglet = indice),
          calendriers: agenda?.calendriers ?? const [],
          surRenommage: agenda == null
              ? null
              : (c) => _renommer(agenda, c, (f) => setState(f)),
          surCreation: agenda == null ? null : () => _creerUnCalendrier(agenda),
          abonnements: agenda?.abonnements ?? const [],
          surAbonnement: agenda == null
              ? null
              : () => _ajouterUnAbonnement(agenda, (f) => setState(f)),
          surDesabonnement: agenda == null
              ? null
              : (a) => _desabonner(agenda, a, (f) => setState(f)),
          masques: agenda?.masques ?? const {},
          surMasques: (m) => agenda?.masquer(m),
          ancre: agenda?.ancre ?? DateTime.now(),
          surJour: (j) {
            setState(() => _onglet = 0);
            agenda?.allerAuJour(j);
          },
        ),
        Expanded(child: pile),
      ],
    );
  }

  /// La barre d'outils du bureau, et l'encoche qu'elle doit s'ajouter.
  ///
  /// Le widget vit dans `barre_de_titre.dart` : sorti d'ici pour qu'un témoin puisse le
  /// monter seul, l'accueil ne se montant pas en test. Voir son en-tête.
  ///
  /// `defaultTargetPlatform` et non `Theme.of(context).platform`, le même nombre que
  /// pour le `removePadding` de [build] : les deux décisions sont la même, et deux
  /// sources les laisseraient diverger.
  PreferredSizeWidget _barreDeTitre(BuildContext context) {
    final agenda = _agenda.currentState;
    return BarreDeTitreDeBureau(
      encoche: BarreDeTitreDeBureau.encocheSelon(
        context,
        defaultTargetPlatform,
      ),
      vue: agenda?.vue ?? VueDAgenda.jour,
      // Une vue choisie ramène l'agenda devant, comme le fait déjà la feuille du menu :
      // changer de vue depuis les Réglages aurait sinon un effet invisible.
      surVue: (v) {
        setState(() => _onglet = 0);
        agenda?.choisirLaVue(v);
      },
      surRecherche: () => _agenda.currentState?.rechercher(),
      peutCreer: agenda?.peutCreer ?? false,
      surNouveau: () => _agenda.currentState?.nouvelEvenement(),
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
                  (VueDAgenda.annee, Icons.calendar_today_outlined),
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
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            l.calendriersAAfficher,
                            style: const TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                        // Le même « + » que la colonne du bureau, au même endroit
                        // relatif : au bout de l'en-tête. La feuille est le seul endroit
                        // où un téléphone gère ses calendriers ; sans ce bouton, créer
                        // resterait réservé au web.
                        IconButton(
                          key: const Key('calendriers.nouveau'),
                          icon: const Icon(Icons.add),
                          tooltip: l.nouveauCalendrier,
                          onPressed: () async {
                            await _creerUnCalendrier(agenda);
                            // La feuille porte sa propre copie de la liste.
                            majour(() {});
                          },
                        ),
                      ],
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
                      // Le crayon vit **dans** le titre, et non en `secondary` : cette
                      // place est prise par la pastille de couleur, qui dit de quel
                      // calendrier il s'agit et qu'on ne peut pas retirer pour faire de
                      // la place. Un `IconButton` absorbe la frappe, donc toucher le
                      // crayon n'allume ni n'éteint la case.
                      title: Row(
                        children: [
                          Expanded(child: Text(c.nom)),
                          if (c.aSoi)
                            IconButton(
                              key: Key('calendriers.renommer.${c.id}'),
                              icon: const Icon(Icons.edit_outlined, size: 18),
                              tooltip: l.renommerLeCalendrier,
                              visualDensity: VisualDensity.compact,
                              onPressed: () => _renommer(agenda, c, majour),
                            ),
                        ],
                      ),
                      value: !masques.contains(c.id),
                      onChanged: (montre) => poser(
                        montre == true
                            ? ({...masques}..remove(c.id))
                            : {...masques, c.id},
                      ),
                    ),
                  // Les abonnements, dans la même feuille et sous leur propre titre.
                  // C'est le seul endroit où un téléphone les gère : sans cette section,
                  // s'abonner et se désabonner resteraient réservés au web, exactement
                  // comme la création d'un calendrier l'était.
                  const Divider(),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(
                      Mesures.marge,
                      4,
                      Mesures.marge,
                      0,
                    ),
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            l.abonnements,
                            style: const TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                        IconButton(
                          key: const Key('abonnements.nouveau'),
                          icon: const Icon(Icons.add),
                          tooltip: l.nouvelAbonnement,
                          onPressed: () => _ajouterUnAbonnement(agenda, majour),
                        ),
                      ],
                    ),
                  ),
                  // La même règle que la colonne du bureau : une section vide le dit,
                  // plutôt que de laisser un intitulé seul au-dessus du vide.
                  if (agenda.abonnements.isEmpty)
                    Padding(
                      padding: const EdgeInsets.fromLTRB(
                        Mesures.marge,
                        0,
                        Mesures.marge,
                        8,
                      ),
                      child: Text(l.aucunAbonnement),
                    ),
                  for (final a in agenda.abonnements)
                    CheckboxListTile(
                      key: Key('abonnements.${a.id}'),
                      secondary: CircleAvatar(
                        radius: 7,
                        backgroundColor: _couleur(a.couleur),
                      ),
                      title: Row(
                        children: [
                          Expanded(child: Text(a.nom)),
                          IconButton(
                            key: Key('abonnements.desabonner.${a.id}'),
                            icon: const Icon(Icons.delete_outline, size: 18),
                            tooltip: l.supprimerLAbonnement,
                            visualDensity: VisualDensity.compact,
                            onPressed: () => _desabonner(agenda, a, majour),
                          ),
                        ],
                      ),
                      subtitle: a.enPanne ? Text(l.abonnementEnPanne) : null,
                      value: !masques.contains(a.id),
                      onChanged: (montre) => poser(
                        montre == true
                            ? ({...masques}..remove(a.id))
                            : {...masques, a.id},
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

  /// Demande un nom et ne referme la boucle qu'une fois le serveur d'accord.
  ///
  /// `majour` est le `setState` du `StatefulBuilder` de la feuille : sans lui, le nom
  /// changerait dans l'état de l'agenda et la feuille continuerait d'afficher l'ancien,
  /// puisqu'elle est reconstruite par son propre constructeur et non par l'écran.
  /// Demande un nom et crée le calendrier, une fois le serveur d'accord.
  ///
  /// Même forme que [_renommer] : la boîte d'abord, l'appel ensuite, et l'erreur dite
  /// là où on l'a provoquée. Un calendrier dont la création échoue en silence laisserait
  /// quelqu'un la refaire trois fois.
  Future<void> _creerUnCalendrier(EcranDAgendaState agenda) async {
    final nom = await demanderUnNomDeCalendrier(context);
    if (nom == null || !mounted) return;
    try {
      await agenda.creerUnCalendrier(nom);
    } on Object catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(lisible(e, L.of(context)))));
    }
  }

  /// Demande un flux et s'y abonne, une fois le serveur d'accord.
  ///
  /// L'erreur est montrée telle quelle et c'est délibéré : le serveur **lit** le flux
  /// avant de l'enregistrer, donc un 422 ici veut dire « cette adresse ne rend pas de
  /// calendrier ». C'est précisément ce que la personne a besoin de savoir, et c'est
  /// perdu si on le remplace par un message générique.
  ///
  /// `majour` est le `setState` de la feuille quand l'appel vient du téléphone : elle
  /// porte sa propre copie de la liste et n'est pas reconstruite par l'écran.
  Future<void> _ajouterUnAbonnement(
    EcranDAgendaState agenda,
    void Function(VoidCallback) majour,
  ) async {
    final flux = await demanderUnAbonnement(context);
    if (flux == null || !mounted) return;
    try {
      await agenda.ajouterUnAbonnement(nom: flux.nom, url: flux.url);
      majour(() {});
    } on Object catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(lisible(e, L.of(context)))));
    }
  }

  /// Se désabonne, après confirmation.
  ///
  /// Une confirmation et pas un geste direct : la corbeille est à côté d'une case à
  /// cocher, et les deux se visent de la même façon. Décocher cache le flux ; supprimer
  /// l'enlève, avec son adresse — qu'il faudrait retrouver chez le fournisseur pour
  /// revenir en arrière. Les deux ne se valent pas, donc elles ne se touchent pas de la
  /// même manière.
  Future<void> _desabonner(
    EcranDAgendaState agenda,
    Abonnement abonnement,
    void Function(VoidCallback) majour,
  ) async {
    final l = L.of(context);
    final confirme = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(l.supprimerLAbonnement),
        content: Text(abonnement.nom),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text(l.annuler),
          ),
          TextButton(
            key: const Key('abonnement.confirmer'),
            onPressed: () => Navigator.of(context).pop(true),
            child: Text(l.supprimer),
          ),
        ],
      ),
    );
    if (confirme != true || !mounted) return;
    try {
      await agenda.supprimerUnAbonnement(abonnement.id);
      majour(() {});
    } on Object catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(lisible(e, L.of(context)))));
    }
  }

  Future<void> _renommer(
    EcranDAgendaState agenda,
    Calendrier calendrier,
    void Function(VoidCallback) majour,
  ) async {
    final nom = await demanderUnNouveauNom(context, nomActuel: calendrier.nom);
    if (nom == null || !mounted) return;
    try {
      await agenda.renommerLeCalendrier(calendrier.id, nom);
      // La feuille porte sa propre copie de la liste : on la redessine.
      majour(() {});
    } on Object catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(lisible(e, L.of(context)))));
    }
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

/// A shortcut matched on the physical key and its modifiers, whatever character the
/// layout puts there.
class _ToucheParPosition extends ShortcutActivator {
  const _ToucheParPosition(this.cle, {this.meta = false, this.control = false});

  final PhysicalKeyboardKey cle;
  final bool meta;
  final bool control;

  @override
  Iterable<LogicalKeyboardKey>? get triggers => null;

  @override
  bool accepts(KeyEvent event, HardwareKeyboard state) =>
      event is KeyDownEvent &&
      event.physicalKey == cle &&
      state.isMetaPressed == meta &&
      state.isControlPressed == control &&
      !state.isAltPressed &&
      !state.isShiftPressed;

  @override
  String debugDescribeKeys() =>
      '${meta ? 'Meta+' : ''}${control ? 'Control+' : ''}${cle.debugName}';
}
