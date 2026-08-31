import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../services/agenda.dart' show ProvenanceDuTitre;
import '../services/session.dart';
import '../services/taches.dart';
import '../theme.dart';

/// Les tâches : ce qui presse d'abord, ce qui est fait à la fin.
class EcranDeTaches extends StatefulWidget {
  const EcranDeTaches({super.key, required this.session});

  final Session session;

  @override
  State<EcranDeTaches> createState() => _EcranDeTachesState();
}

class _EcranDeTachesState extends State<EcranDeTaches> {
  List<Tache>? _taches;
  String? _erreur;
  bool _montrerLesFaites = false;

  @override
  void initState() {
    super.initState();
    _recharger();
  }

  Taches? get _service {
    final api = widget.session.api;
    final auth = widget.session.auth;
    if (api == null || auth == null) return null;
    return Taches(api: api, auth: auth);
  }

  Future<void> _recharger() async {
    final service = _service;
    final organisation = widget.session.organisation;
    if (service == null || organisation == null) return;
    setState(() => _erreur = null);
    try {
      final taches = await service.lister(organisation: organisation);
      if (mounted) setState(() => _taches = taches);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    }
  }

  Future<void> _basculer(Tache tache) async {
    final service = _service;
    if (service == null) return;
    // On bascule d'abord à l'écran : cocher une case doit répondre tout de suite, et
    // l'appel qui suit ne change rien de visible s'il réussit.
    setState(() {
      _taches = Taches.ordonner([
        for (final t in _taches ?? <Tache>[])
          if (t.id == tache.id)
            Tache(
              id: t.id,
              provenance: t.provenance,
              titre: t.titre,
              notes: t.notes,
              echeance: t.echeance,
              faite: !t.faite,
              creee: t.creee,
            )
          else
            t,
      ]);
    });
    try {
      await service.marquer(tache.id, faite: !tache.faite);
    } on Object catch (e) {
      // L'écran mentait : on le remet d'accord avec le serveur, et on le dit.
      if (mounted) setState(() => _erreur = '$e');
      await _recharger();
    }
  }

  Future<void> _nouvelle() async {
    final cree = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _FeuilleDeNouvelleTache(session: widget.session),
    );
    if (cree == true) await _recharger();
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final toutes = _taches;
    final visibles = toutes == null
        ? null
        : [for (final t in toutes) if (_montrerLesFaites || !t.faite) t];
    final faites = toutes?.where((t) => t.faite).length ?? 0;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Tâches'),
        actions: [
          if (faites > 0)
            TextButton(
              onPressed: () => setState(() => _montrerLesFaites = !_montrerLesFaites),
              child: Text(_montrerLesFaites ? 'Masquer les faites' : 'Faites ($faites)'),
            ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        // `IndexedStack` garde **tous** les onglets vivants : deux boutons flottants
        // coexistent donc en permanence, et l'étiquette par défaut est la même pour les
        // deux. Flutter lève alors « multiple heroes share the same tag » à chaque
        // animation — une exception répétée, qui n'empêche pas l'affichage mais perturbe
        // la mise en page et les gestes.
        heroTag: 'taches',
        onPressed: _nouvelle,
        tooltip: 'Nouvelle tâche',
        child: const Icon(Icons.add),
      ),
      body: RefreshIndicator(
        onRefresh: _recharger,
        child: _corps(gc, visibles),
      ),
    );
  }

  Widget _corps(Gc gc, List<Tache>? visibles) {
    if (_erreur != null) {
      return ListView(
        padding: const EdgeInsets.all(20),
        children: [Text(_erreur!, style: TextStyle(color: gc.danger))],
      );
    }
    if (visibles == null) return const Center(child: CircularProgressIndicator());
    if (visibles.isEmpty) {
      return ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(
            _montrerLesFaites ? 'Aucune tâche.' : 'Rien à faire.',
            style: TextStyle(color: gc.estompe),
          ),
        ],
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: visibles.length,
      separatorBuilder: (_, _) => Divider(height: 1, color: gc.bordure),
      itemBuilder: (_, i) => _ligne(gc, visibles[i]),
    );
  }

  Widget _ligne(Gc gc, Tache tache) {
    // La règle qui traverse la suite : ce qui ne se déchiffre pas s'affiche quand même.
    // Une tâche absente se lit comme « rien à faire », ce qui est faux.
    final (titre, style) = switch (tache.provenance) {
      ProvenanceDuTitre.dechiffre || ProvenanceDuTitre.enClair => (
          tache.titre,
          TextStyle(
            color: tache.faite ? gc.estompe : gc.encre,
            decoration: tache.faite ? TextDecoration.lineThrough : null,
          )
        ),
      ProvenanceDuTitre.illisible => (
          'Contenu illisible — clé manquante',
          TextStyle(color: gc.danger, fontStyle: FontStyle.italic)
        ),
      ProvenanceDuTitre.sansTitre => (
          'Sans titre',
          TextStyle(color: gc.estompe, fontStyle: FontStyle.italic)
        ),
    };

    final enRetard = tache.enRetard(DateTime.now());
    final echeance = tache.echeance;
    return ListTile(
      leading: Checkbox(
        value: tache.faite,
        onChanged: (_) => _basculer(tache),
      ),
      title: Text(titre, style: style),
      subtitle: echeance == null && tache.notes == null
          ? null
          : Text(
              [
                if (echeance != null) DateFormat.yMMMd('fr_FR').format(echeance),
                if (tache.notes != null) tache.notes!,
              ].join(' · '),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 12,
                // Le retard se voit ; il ne se déduit pas d'une date qu'il faudrait
                // comparer soi-même à celle du jour.
                color: enRetard ? gc.danger : gc.estompe,
              ),
            ),
      trailing: enRetard ? Icon(Icons.error_outline, size: 18, color: gc.danger) : null,
      onLongPress: () => _supprimer(tache),
    );
  }

  Future<void> _supprimer(Tache tache) async {
    final service = _service;
    if (service == null) return;
    final confirme = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Supprimer cette tâche ?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(c, false), child: const Text('Annuler')),
          TextButton(
              onPressed: () => Navigator.pop(c, true), child: const Text('Supprimer')),
        ],
      ),
    );
    if (confirme != true) return;
    try {
      await service.supprimer(tache.id);
      await _recharger();
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    }
  }
}

class _FeuilleDeNouvelleTache extends StatefulWidget {
  const _FeuilleDeNouvelleTache({required this.session});

  final Session session;

  @override
  State<_FeuilleDeNouvelleTache> createState() => _FeuilleDeNouvelleTacheState();
}

class _FeuilleDeNouvelleTacheState extends State<_FeuilleDeNouvelleTache> {
  final _titre = TextEditingController();
  final _notes = TextEditingController();
  DateTime? _echeance;
  bool _occupe = false;
  String? _erreur;

  @override
  void dispose() {
    _titre.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _enregistrer() async {
    final api = widget.session.api;
    final auth = widget.session.auth;
    final organisation = widget.session.organisation;
    if (api == null || auth == null || organisation == null) return;
    setState(() {
      _occupe = true;
      _erreur = null;
    });
    try {
      await Taches(api: api, auth: auth).creer(
        titre: _titre.text,
        notes: _notes.text,
        echeance: _echeance,
        organisation: organisation,
      );
      if (mounted) Navigator.of(context).pop(true);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    } finally {
      if (mounted) setState(() => _occupe = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 20,
        // Sans cela, le clavier recouvre le bouton d'enregistrement.
        bottom: MediaQuery.of(context).viewInsets.bottom + 20,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Nouvelle tâche',
              style: TextStyle(
                  fontSize: 18, fontWeight: FontWeight.bold, color: gc.encre)),
          const SizedBox(height: 16),
          TextField(
            controller: _titre,
            autofocus: true,
            // Le bouton dépend de ce champ : sans ce rappel, il resterait éteint
            // jusqu'à ce qu'autre chose provoque un rafraîchissement.
            onChanged: (_) => setState(() {}),
            decoration: const InputDecoration(hintText: 'Titre'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _notes,
            maxLines: 3,
            decoration: const InputDecoration(hintText: 'Notes'),
          ),
          const SizedBox(height: 12),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: Icon(Icons.event_outlined, color: gc.estompe),
            title: Text(
              _echeance == null
                  ? 'Sans échéance'
                  : DateFormat.yMMMMd('fr_FR').format(_echeance!),
              style: TextStyle(color: gc.encre),
            ),
            trailing: _echeance == null
                ? null
                : IconButton(
                    icon: const Icon(Icons.close),
                    tooltip: "Retirer l'échéance",
                    onPressed: () => setState(() => _echeance = null),
                  ),
            onTap: () async {
              final date = await showDatePicker(
                context: context,
                initialDate: _echeance ?? DateTime.now(),
                firstDate: DateTime(2000),
                lastDate: DateTime(2100),
              );
              if (date != null) setState(() => _echeance = date);
            },
          ),
          if (_erreur != null) ...[
            const SizedBox(height: 12),
            Text(_erreur!, style: TextStyle(color: gc.danger, fontSize: 13)),
          ],
          const SizedBox(height: 16),
          BoutonPrincipal(
            onPressed: _occupe || _titre.text.trim().isEmpty ? null : _enregistrer,
            child: _occupe
                ? const SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Gc.surAccent))
                : const Text('Créer'),
          ),
        ],
      ),
    );
  }
}
