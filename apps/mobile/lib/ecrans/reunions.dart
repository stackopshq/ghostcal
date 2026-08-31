import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../services/reunions.dart';
import '../services/session.dart';
import '../theme.dart';

/// Les réunions réservées, à venir ou passées.
class EcranDeReunions extends StatefulWidget {
  const EcranDeReunions({super.key, required this.session});

  final Session session;

  @override
  State<EcranDeReunions> createState() => _EcranDeReunionsState();
}

class _EcranDeReunionsState extends State<EcranDeReunions> {
  PorteeDesReunions _portee = PorteeDesReunions.aVenir;
  List<Reunion>? _reunions;
  String? _erreur;

  @override
  void initState() {
    super.initState();
    _recharger();
  }

  Reunions? get _service {
    final api = widget.session.api;
    final auth = widget.session.auth;
    if (api == null || auth == null) return null;
    return Reunions(api: api, auth: auth);
  }

  Future<void> _recharger() async {
    final service = _service;
    final organisation = widget.session.organisation;
    if (service == null || organisation == null) return;
    setState(() {
      _erreur = null;
      _reunions = null;
    });
    try {
      final reunions = await service.lister(_portee, organisation: organisation);
      if (mounted) setState(() => _reunions = reunions);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Réunions'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(48),
          child: Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: SegmentedButton<PorteeDesReunions>(
              segments: const [
                ButtonSegment(value: PorteeDesReunions.aVenir, label: Text('À venir')),
                ButtonSegment(value: PorteeDesReunions.passees, label: Text('Passées')),
              ],
              selected: {_portee},
              onSelectionChanged: (choix) {
                setState(() => _portee = choix.first);
                _recharger();
              },
            ),
          ),
        ),
      ),
      body: RefreshIndicator(onRefresh: _recharger, child: _corps(gc)),
    );
  }

  Widget _corps(Gc gc) {
    if (_erreur != null) {
      return ListView(
        padding: const EdgeInsets.all(20),
        children: [Text(_erreur!, style: TextStyle(color: gc.danger))],
      );
    }
    final reunions = _reunions;
    if (reunions == null) return const Center(child: CircularProgressIndicator());
    if (reunions.isEmpty) {
      return ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(
            _portee == PorteeDesReunions.aVenir
                ? 'Aucune réunion à venir.'
                : 'Aucune réunion passée.',
            style: TextStyle(color: gc.estompe),
          ),
        ],
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: reunions.length,
      separatorBuilder: (_, _) => Divider(height: 1, color: gc.bordure),
      itemBuilder: (_, i) => _ligne(gc, reunions[i]),
    );
  }

  Widget _ligne(Gc gc, Reunion reunion) {
    final annulee = reunion.statut == StatutDeReunion.annulee;
    return ListTile(
      title: Text(
        reunion.intitule,
        style: TextStyle(
          color: annulee ? gc.estompe : gc.encre,
          decoration: annulee ? TextDecoration.lineThrough : null,
        ),
      ),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${DateFormat.yMMMEd('fr_FR').format(reunion.debut)}'
            ' · ${DateFormat.Hm().format(reunion.debut)}'
            '–${DateFormat.Hm().format(reunion.fin)}',
            style: TextStyle(fontSize: 12, color: gc.estompe),
          ),
          _quiEstCe(gc, reunion),
        ],
      ),
      trailing: annulee
          ? Text('Annulée', style: TextStyle(fontSize: 12, color: gc.danger))
          : const Icon(Icons.chevron_right),
      onTap: () => _detail(reunion),
    );
  }

  /// Qui a réservé, et ce qu'on sait en dire.
  ///
  /// Quatre provenances, parce que les aplatir afficherait « Sans nom » là où le nom
  /// existe, chiffré, juste à côté — ou un aveu d'échec là où l'adresse suffit à
  /// identifier la personne.
  Widget _quiEstCe(Gc gc, Reunion reunion) {
    final (texte, style) = switch (reunion.provenanceDuNom) {
      NomDInvite.enClair || NomDInvite.dechiffre => (
          reunion.courriel.isEmpty
              ? reunion.nom
              : '${reunion.nom} · ${reunion.courriel}',
          TextStyle(fontSize: 12, color: gc.estompe)
        ),
      NomDInvite.illisible => (
          reunion.courriel.isEmpty
              ? 'Identité illisible — clé manquante'
              : '${reunion.courriel} · nom illisible',
          TextStyle(fontSize: 12, color: gc.danger)
        ),
      NomDInvite.inconnu => (
          reunion.courriel.isEmpty ? 'Invité inconnu' : reunion.courriel,
          TextStyle(fontSize: 12, color: gc.estompe, fontStyle: FontStyle.italic)
        ),
    };
    return Text(texte, style: style, maxLines: 1, overflow: TextOverflow.ellipsis);
  }

  void _detail(Reunion reunion) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _FeuilleDeReunion(
        reunion: reunion,
        annuler: reunion.statut == StatutDeReunion.annulee ? null : () => _annuler(reunion),
      ),
    );
  }

  Future<void> _annuler(Reunion reunion) async {
    final service = _service;
    if (service == null) return;
    try {
      await service.annuler(reunion.id);
      await _recharger();
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    }
  }
}

class _FeuilleDeReunion extends StatelessWidget {
  const _FeuilleDeReunion({required this.reunion, this.annuler});

  final Reunion reunion;
  final VoidCallback? annuler;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(reunion.intitule,
                style: TextStyle(
                    fontSize: 18, fontWeight: FontWeight.bold, color: gc.encre)),
            const SizedBox(height: 4),
            Text(
              '${DateFormat.yMMMMEEEEd('fr_FR').format(reunion.debut)} · '
              '${DateFormat.Hm().format(reunion.debut)}–${DateFormat.Hm().format(reunion.fin)}',
              style: TextStyle(color: gc.estompe, fontSize: 13),
            ),
            // Le fuseau de l'invité, pas le nôtre : c'est dans celui-là qu'il a lu
            // l'heure au moment de réserver, et c'est ce qu'il faut savoir avant de lui
            // proposer un report.
            Text('Fuseau de l’invité : ${reunion.fuseau}',
                style: TextStyle(color: gc.estompe, fontSize: 12)),
            if (reunion.lieu != null) ...[
              const SizedBox(height: 12),
              _ligne(gc, Icons.place_outlined, reunion.lieu!),
            ],
            if (reunion.adresse != null)
              _ligne(gc, Icons.videocam_outlined, reunion.adresse!.toString()),
            if (reunion.courriel.isNotEmpty)
              _ligne(gc, Icons.mail_outline, reunion.courriel),
            if (reunion.reponses.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text('RÉPONSES',
                  style: TextStyle(
                      color: gc.estompe,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 1.1)),
              const SizedBox(height: 8),
              for (final reponse in reunion.reponses)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(reponse.key,
                          style: TextStyle(fontSize: 12, color: gc.estompe)),
                      Text(reponse.value, style: TextStyle(color: gc.encre)),
                    ],
                  ),
                ),
            ],
            if (reunion.notes != null) ...[
              const SizedBox(height: 12),
              Text('NOTES',
                  style: TextStyle(
                      color: gc.estompe,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 1.1)),
              const SizedBox(height: 4),
              Text(reunion.notes!, style: TextStyle(color: gc.encre)),
            ],
            if (annuler != null) ...[
              const SizedBox(height: 20),
              TextButton.icon(
                onPressed: () async {
                  final confirme = await showDialog<bool>(
                    context: context,
                    builder: (c) => AlertDialog(
                      title: const Text('Annuler cette réunion ?'),
                      content: const Text(
                          'L’invité en sera informé par le serveur.'),
                      actions: [
                        TextButton(
                            onPressed: () => Navigator.pop(c, false),
                            child: const Text('Retour')),
                        TextButton(
                            onPressed: () => Navigator.pop(c, true),
                            child: const Text('Annuler la réunion')),
                      ],
                    ),
                  );
                  if (confirme != true) return;
                  if (context.mounted) Navigator.of(context).pop();
                  annuler!();
                },
                icon: Icon(Icons.event_busy, color: gc.danger),
                label: Text('Annuler la réunion', style: TextStyle(color: gc.danger)),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _ligne(Gc gc, IconData icone, String texte) => Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icone, size: 16, color: gc.estompe),
            const SizedBox(width: 8),
            Expanded(child: Text(texte, style: TextStyle(color: gc.encre, fontSize: 13))),
          ],
        ),
      );
}
