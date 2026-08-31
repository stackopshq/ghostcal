import 'package:flutter/material.dart';

import '../services/session.dart';
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
    return Scaffold(
      body: IndexedStack(
        index: _onglet,
        children: [
          EcranDAgenda(session: widget.session),
          EcranDeReglages(session: widget.session),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _onglet,
        onDestinationSelected: (i) => setState(() => _onglet = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.calendar_today), label: 'Agenda'),
          NavigationDestination(icon: Icon(Icons.settings), label: 'Réglages'),
        ],
      ),
    );
  }
}
