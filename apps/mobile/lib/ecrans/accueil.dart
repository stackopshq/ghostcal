import 'package:flutter/material.dart';

import '../services/session.dart';
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
  });

  final Session session;
  final Verrouillage verrouillage;

  @override
  State<EcranDAccueil> createState() => _EcranDAccueilState();
}

class _EcranDAccueilState extends State<EcranDAccueil>
    with WidgetsBindingObserver {
  int _onglet = 0;
  DateTime? _partiEnArrierePlan;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
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
        // `ContenuBorne` ici et pas autour du `Scaffold` : la barre d'onglets, plus bas,
        // doit garder toute la largeur. La borner la centrerait sur 560 points au milieu
        // d'un iPad, ce qui est plus laid que l'étirement qu'on corrige.
        body: ContenuBorne(
          child: IndexedStack(
            index: _onglet,
            children: [
              EcranDAgenda(
                session: widget.session,
                verrouillage: widget.verrouillage,
              ),
              EcranDeTaches(session: widget.session),
              EcranDeReunions(session: widget.session),
              EcranDeTypesDeRendezVous(session: widget.session),
              EcranDeReglages(
                session: widget.session,
                verrouillage: widget.verrouillage,
              ),
            ],
          ),
        ),
        bottomNavigationBar: NavigationBar(
          // Transparente pour laisser passer le fond ; sans cela une bande opaque
          // couperait le dégradé net au bas de chaque écran.
          backgroundColor: Colors.transparent,
          surfaceTintColor: Colors.transparent,
          indicatorColor: Gc.of(context).accent.withValues(alpha: 0.18),
          selectedIndex: _onglet,
          onDestinationSelected: (i) => setState(() => _onglet = i),
          // `const` a sauté : les libellés viennent maintenant de `L.of(context)`, qui
          // dépend du contexte et ne peut donc pas être constant. Le laisser ferait
          // échouer la compilation sur « Arguments of a constant creation must be
          // constant expressions », un message qui ne nomme pas la cause.
          destinations: [
            NavigationDestination(
              icon: const Icon(Icons.calendar_today),
              label: L.of(context).ongletAgenda,
            ),
            NavigationDestination(
              icon: const Icon(Icons.check_circle_outline),
              label: L.of(context).ongletTaches,
            ),
            NavigationDestination(
              icon: const Icon(Icons.groups_outlined),
              label: L.of(context).ongletReunions,
            ),
            NavigationDestination(
              icon: const Icon(Icons.event_available_outlined),
              label: L.of(context).ongletRdv,
            ),
            NavigationDestination(
              icon: const Icon(Icons.settings),
              label: L.of(context).ongletReglages,
            ),
          ],
        ),
      ),
    );
  }
}
