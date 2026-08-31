import 'package:flutter/material.dart';

import '../services/session.dart';
import '../services/verrouillage.dart';
import '../theme.dart';
import 'agenda.dart';
import 'reglages.dart';
import 'reunions.dart';
import 'types_de_rendez_vous.dart';
import 'taches.dart';

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

class _EcranDAccueilState extends State<EcranDAccueil> with WidgetsBindingObserver {
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
        body: IndexedStack(
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
        bottomNavigationBar: NavigationBar(
          // Transparente pour laisser passer le fond ; sans cela une bande opaque
          // couperait le dégradé net au bas de chaque écran.
          backgroundColor: Colors.transparent,
          surfaceTintColor: Colors.transparent,
          indicatorColor: Gc.of(context).accent.withValues(alpha: 0.18),
          selectedIndex: _onglet,
          onDestinationSelected: (i) => setState(() => _onglet = i),
          destinations: const [
            NavigationDestination(icon: Icon(Icons.calendar_today), label: 'Agenda'),
            NavigationDestination(icon: Icon(Icons.check_circle_outline), label: 'Tâches'),
            NavigationDestination(icon: Icon(Icons.groups_outlined), label: 'Réunions'),
            NavigationDestination(icon: Icon(Icons.event_available_outlined), label: 'RDV'),
            NavigationDestination(icon: Icon(Icons.settings), label: 'Réglages'),
          ],
        ),
      ),
    );
  }
}
