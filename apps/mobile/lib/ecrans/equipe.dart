import 'package:flutter/material.dart';

import '../services/reglages.dart';
import '../services/session.dart';
import '../theme.dart';

/// Les membres de l'organisation, et ce qu'on peut leur faire.
class EcranDEquipe extends StatefulWidget {
  const EcranDEquipe({super.key, required this.session});

  final Session session;

  @override
  State<EcranDEquipe> createState() => _EcranDEquipeState();
}

class _EcranDEquipeState extends State<EcranDEquipe> {
  List<Membre>? _membres;
  String? _erreur;

  @override
  void initState() {
    super.initState();
    _charger();
  }

  Reglages? get _service {
    final api = widget.session.api;
    return api == null ? null : Reglages(api: api);
  }

  Future<void> _charger() async {
    final service = _service;
    if (service == null) return;
    setState(() => _erreur = null);
    try {
      final membres = await service.membres();
      if (mounted) setState(() => _membres = membres);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    }
  }

  Future<void> _changerLeRole(Membre membre, String role) async {
    final service = _service;
    if (service == null) return;
    try {
      // Le serveur rend la liste à jour : on la réutilise plutôt que de relire, sinon
      // deux appels donneraient deux vérités possibles entre-temps.
      final membres = await service.changerLeRole(membre.id, role: role);
      if (mounted) setState(() => _membres = membres);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    }
  }

  Future<void> _retirer(Membre membre) async {
    final service = _service;
    if (service == null) return;
    final confirme = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text('Retirer ${membre.nom.isEmpty ? membre.courriel : membre.nom} ?'),
        content: const Text(
            'Cette personne perdra l’accès aux calendriers de l’organisation.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Annuler')),
          TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('Retirer')),
        ],
      ),
    );
    if (confirme != true) return;
    try {
      await service.retirerLeMembre(membre.id);
      await _charger();
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final membres = _membres;
    // `FondGhost` parce que cet écran est **poussé** sur la pile, et non logé dans
    // `EcranDAccueil`.
    //
    // Le thème pose `scaffoldBackgroundColor: Colors.transparent` — délibérément : le
    // fond est peint par `FondGhost`, qu'un Scaffold opaque masquerait. Les cinq onglets
    // en héritent, `EcranDAccueil` les enveloppant tous. Un écran poussé est frère de
    // celui-là dans la pile, pas son enfant : il n'hérite de rien, et son Scaffold
    // transparent laissait voir le noir du dessous.
    //
    // Le symptôme ne ressemblait pas à un fond manquant : en thème clair, les champs
    // restaient blancs sur noir et les libellés — encre foncée — devenaient presque
    // illisibles. Cela se lit comme un thème sombre mal fichu, pas comme un fond absent.
    // Vu sur une capture d'écran ; aucun test ne le voyait.
    return FondGhost(
      child: Scaffold(
        appBar: AppBar(title: const Text('Équipe')),
        body: RefreshIndicator(
          onRefresh: _charger,
          child: _erreur != null
              ? ListView(
                  padding: const EdgeInsets.all(20),
                  children: [Text(_erreur!, style: TextStyle(color: gc.danger))],
                )
              : membres == null
                  ? const Center(child: CircularProgressIndicator())
                  : ListView.separated(
                      itemCount: membres.length,
                      separatorBuilder: (_, _) => Divider(height: 1, color: gc.bordure),
                      itemBuilder: (_, i) => _ligne(gc, membres[i]),
                    ),
        ),
    ),
    );
  }

  Widget _ligne(Gc gc, Membre membre) {
    // Le propriétaire ne se modifie pas depuis ici : lui retirer son rôle ou le sortir de
    // l'organisation pourrait laisser celle-ci sans personne pour l'administrer.
    final modifiable = membre.role != 'owner';
    return ListTile(
      title: Text(membre.nom.isEmpty ? membre.courriel : membre.nom),
      subtitle: Text(
        membre.nom.isEmpty ? membre.roleLisible : '${membre.courriel} · ${membre.roleLisible}',
        style: TextStyle(fontSize: 12, color: gc.estompe),
      ),
      trailing: !modifiable
          ? Icon(Icons.shield_outlined, size: 18, color: gc.estompe)
          : PopupMenuButton<String>(
              itemBuilder: (_) => [
                const PopupMenuItem(value: 'admin', child: Text('Administrateur')),
                const PopupMenuItem(value: 'member', child: Text('Membre')),
                const PopupMenuItem(value: '-', child: Text("Retirer de l'équipe")),
              ],
              onSelected: (choix) =>
                  choix == '-' ? _retirer(membre) : _changerLeRole(membre, choix),
            ),
    );
  }
}
