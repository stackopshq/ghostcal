import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../services/agenda.dart';
import '../services/session.dart';
import '../services/verrouillage.dart';
import '../theme.dart';
import 'nouvel_evenement.dart';

/// L'agenda du jour, jour par jour.
///
/// On demande une fenêtre étroite et on la déplace, plutôt que de tout charger : le
/// serveur borne la plage à 366 jours parce qu'un événement récurrent développé sur une
/// plage illimitée serait un déni de service.
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
  DateTime _jour = DateTime.now();
  List<LigneDAgenda>? _lignes;
  List<Calendrier> _calendriers = const [];
  String? _erreur;
  bool _charge = false;

  @override
  void initState() {
    super.initState();
    _recharger();
  }

  Agenda? get _agenda {
    final api = widget.session.api;
    final auth = widget.session.auth;
    if (api == null || auth == null) return null;
    return Agenda(api: api, auth: auth);
  }

  Future<void> _recharger() async {
    final agenda = _agenda;
    final organisation = widget.session.organisation;
    if (agenda == null || organisation == null) return;
    setState(() {
      _charge = true;
      _erreur = null;
    });
    try {
      final debut = DateTime(_jour.year, _jour.month, _jour.day);
      final lignes = await agenda.lignes(
        de: debut,
        a: debut.add(const Duration(days: 1)),
        organisation: organisation,
      );
      // Les calendriers ne changent pas d'un jour à l'autre : on ne les redemande qu'une
      // fois, sinon chaque flèche de navigation ferait deux appels au lieu d'un.
      if (_calendriers.isEmpty) _calendriers = await agenda.calendriers();
      if (mounted) setState(() => _lignes = lignes);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    } finally {
      if (mounted) setState(() => _charge = false);
    }
  }

  void _deplacer(int jours) {
    setState(() => _jour = _jour.add(Duration(days: jours)));
    _recharger();
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final inscriptibles = _calendriers.where((c) => c.inscriptible).toList();
    return Scaffold(
      appBar: AppBar(
        title: Text(DateFormat.yMMMMEEEEd('fr_FR').format(_jour)),
        actions: [
          // Un cadenas plutôt que « Verrouiller » : la barre porte déjà trois flèches et
          // une date longue, et le mot y prendrait la place des jours.
          //
          // Il **n'apparaît que si le verrouillage automatique attend**. Avec le réglage
          // par défaut — immédiat — quitter l'application referme déjà le coffre, et le
          // bouton occuperait la meilleure place pour un geste que le système fait tout
          // seul. Dès qu'un délai est réglé, il redevient le seul moyen de verrouiller
          // sur-le-champ.
          if (widget.verrouillage.cadenasVisible)
            IconButton(
              icon: const Icon(Icons.lock_outline),
              tooltip: 'Verrouiller le coffre',
              onPressed: widget.session.verrouiller,
            ),
          IconButton(
            icon: const Icon(Icons.chevron_left),
            tooltip: 'Jour précédent',
            onPressed: () => _deplacer(-1),
          ),
          IconButton(
            icon: const Icon(Icons.today),
            tooltip: "Aujourd'hui",
            onPressed: () {
              setState(() => _jour = DateTime.now());
              _recharger();
            },
          ),
          IconButton(
            icon: const Icon(Icons.chevron_right),
            tooltip: 'Jour suivant',
            onPressed: () => _deplacer(1),
          ),
        ],
      ),
      // Le bouton n'apparaît que s'il existe un calendrier où écrire : un calendrier
      // partagé peut être en lecture seule, et proposer d'y écrire ferait échouer
      // l'enregistrement après que tout a été saisi.
      floatingActionButton: inscriptibles.isEmpty
          ? null
          : FloatingActionButton(
              tooltip: 'Nouvel événement',
              onPressed: () async {
                final cree = await Navigator.of(context).push<bool>(
                  MaterialPageRoute(
                    builder: (_) => EcranDeNouvelEvenement(
                      session: widget.session,
                      calendriers: inscriptibles,
                      jour: _jour,
                    ),
                  ),
                );
                if (cree == true) await _recharger();
              },
              child: const Icon(Icons.add),
            ),
      body: RefreshIndicator(
        onRefresh: _recharger,
        child: _corps(gc),
      ),
    );
  }

  Widget _corps(Gc gc) {
    if (_erreur != null) {
      return ListView(
        padding: const EdgeInsets.all(20),
        children: [Text(_erreur!, style: TextStyle(color: gc.danger))],
      );
    }
    final lignes = _lignes;
    if (lignes == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (lignes.isEmpty) {
      return ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text('Rien ce jour-là.', style: TextStyle(color: gc.estompe)),
          if (_charge) const LinearProgressIndicator(),
        ],
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: lignes.length,
      separatorBuilder: (_, _) => Divider(height: 1, color: gc.bordure),
      itemBuilder: (_, i) => _ligne(gc, lignes[i]),
    );
  }

  Widget _ligne(Gc gc, LigneDAgenda ligne) {
    final heure = ligne.journeeEntiere
        ? 'Journée'
        : '${DateFormat.Hm().format(ligne.debut)} – ${DateFormat.Hm().format(ligne.fin)}';

    // La règle qui traverse toute la suite : ce qui ne se déchiffre pas s'affiche quand
    // même. Une ligne absente se lit comme « libre », ce qui est faux et coûte un
    // rendez-vous double.
    final (titre, style) = switch (ligne.provenance) {
      ProvenanceDuTitre.dechiffre => (ligne.titre, TextStyle(color: gc.encre)),
      ProvenanceDuTitre.enClair => (ligne.titre, TextStyle(color: gc.encre)),
      ProvenanceDuTitre.illisible => (
          'Contenu illisible — clé manquante',
          TextStyle(color: gc.danger, fontStyle: FontStyle.italic)
        ),
      ProvenanceDuTitre.sansTitre => (
          'Sans titre',
          TextStyle(color: gc.estompe, fontStyle: FontStyle.italic)
        ),
    };

    return ListTile(
      title: Text(titre, style: style),
      subtitle: Text(
        [heure, if (ligne.lieu != null) ligne.lieu!].join(' · '),
        style: TextStyle(color: gc.estompe, fontSize: 12),
      ),
      // Une occurrence de série ou un créneau venu d'un calendrier externe n'ont pas
      // d'identifiant d'événement : ils s'affichent mais ne se modifient pas.
      trailing: ligne.evenement == null
          ? Icon(Icons.lock_outline, size: 16, color: gc.estompe)
          : const Icon(Icons.chevron_right),
      onTap: ligne.evenement == null
          ? null
          : () async {
              final modifie = await Navigator.of(context).push<bool>(
                MaterialPageRoute(
                  builder: (_) => EcranDeNouvelEvenement(
                    session: widget.session,
                    calendriers: _calendriers.where((c) => c.inscriptible).toList(),
                    jour: ligne.debut,
                    evenement: ligne.evenement,
                  ),
                ),
              );
              if (modifie == true) await _recharger();
            },
    );
  }
}
