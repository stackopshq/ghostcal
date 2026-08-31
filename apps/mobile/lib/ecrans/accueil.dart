import 'package:flutter/material.dart';

import '../services/session.dart';
import '../theme.dart';
import 'agenda.dart';
import 'reglages.dart';

/// L'application une fois le coffre ouvert.
///
/// Deux onglets seulement, parce que deux fonctions seulement existent. Le client natif en
/// a cinq ; en afficher cinq ici, dont trois vides, laisserait croire à un chargement
/// perpétuel plutôt qu'à un portage en cours.
class EcranDAccueil extends StatefulWidget {
  const EcranDAccueil({super.key, required this.session});

  final Session session;

  @override
  State<EcranDAccueil> createState() => _EcranDAccueilState();
}

class _EcranDAccueilState extends State<EcranDAccueil> {
  int _onglet = 0;

  @override
  Widget build(BuildContext context) {
    return FondGhost(
      child: Scaffold(
        body: IndexedStack(
          index: _onglet,
          children: [
            EcranDAgenda(session: widget.session),
            EcranDeReglages(session: widget.session),
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
            NavigationDestination(icon: Icon(Icons.settings), label: 'Réglages'),
          ],
        ),
      ),
    );
  }
}
