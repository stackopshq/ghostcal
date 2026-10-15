import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../services/api.dart' show ErreurAPI;
import '../services/erreurs.dart';
import '../services/reunions.dart';
import '../services/session.dart';
import '../outils/dates.dart';
import '../theme.dart';
import 'agenda_vues.dart' show heureCourte;
import '../l10n/generated/app_localisations.dart';

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
      if (mounted) setState(() => _erreur = lisible(e, L.of(context)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(L.of(context).ongletReunions),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(48),
          child: Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: SegmentedButton<PorteeDesReunions>(
              segments: [
                ButtonSegment(value: PorteeDesReunions.aVenir, label: Text(L.of(context).aVenir)),
                ButtonSegment(value: PorteeDesReunions.passees, label: Text(L.of(context).passees)),
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
                ? L.of(context).aucuneReunionAVenir
                : L.of(context).aucuneReunionPassee,
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
            '${DateFormat.yMMMEd(langueDesDates(context)).format(reunion.debut)}'
            ' · ${DateFormat.Hm().format(reunion.debut)}'
            '–${DateFormat.Hm().format(reunion.fin)}',
            style: TextStyle(fontSize: 12, color: gc.estompe),
          ),
          _quiEstCe(gc, reunion),
        ],
      ),
      trailing: annulee
          ? Text(L.of(context).annulee, style: TextStyle(fontSize: 12, color: gc.danger))
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
              ? L.of(context).identiteIllisible
              : '${reunion.courriel} · nom illisible',
          TextStyle(fontSize: 12, color: gc.danger)
        ),
      NomDInvite.inconnu => (
          reunion.courriel.isEmpty ? L.of(context).inviteInconnu : reunion.courriel,
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
        envoyerLeLien: reunion.statut == StatutDeReunion.annulee ||
                reunion.debut.isBefore(DateTime.now())
            ? null
            : (lien) async {
                await _service!.envoyerLeLien(reunion.id, lien);
                await _recharger();
              },
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
      if (mounted) setState(() => _erreur = lisible(e, L.of(context)));
    }
  }
}

class _FeuilleDeReunion extends StatefulWidget {
  const _FeuilleDeReunion({required this.reunion, this.annuler, this.envoyerLeLien});

  final Reunion reunion;
  final VoidCallback? annuler;

  /// Sends the video link; `null` for a past or cancelled meeting.
  final Future<void> Function(String lien)? envoyerLeLien;

  @override
  State<_FeuilleDeReunion> createState() => _FeuilleDeReunionState();
}

class _FeuilleDeReunionState extends State<_FeuilleDeReunion> {
  late final _lien = TextEditingController(text: widget.reunion.adresse?.toString() ?? '');
  bool _formulaire = false;
  bool _envoi = false;
  String? _message;
  bool _messageOk = false;

  Reunion get reunion => widget.reunion;
  VoidCallback? get annuler => widget.annuler;

  @override
  void dispose() {
    _lien.dispose();
    super.dispose();
  }

  Future<void> _envoyer() async {
    final lien = _lien.text.trim();
    final l = L.of(context);
    if (!lien.startsWith('https://')) {
      setState(() {
        _message = l.lienDoitCommencerParHttps;
        _messageOk = false;
      });
      return;
    }
    setState(() {
      _envoi = true;
      _message = null;
    });
    try {
      await widget.envoyerLeLien!(lien);
      if (mounted) {
        setState(() {
          _message = l.lienEnvoye;
          _messageOk = true;
          _formulaire = false;
        });
      }
    } on ErreurAPI catch (e) {
      if (mounted) {
        setState(() {
          _message = switch (e.statut) {
            422 => l.lienDoitCommencerParHttps,
            // Saved, but the mail provider failed: the host can resend.
            502 => l.lienEnregistreMailEchoue,
            _ => lisible(e, l),
          };
          _messageOk = false;
        });
      }
    } on Object catch (e) {
      if (mounted) setState(() => _message = lisible(e, l));
    } finally {
      if (mounted) setState(() => _envoi = false);
    }
  }

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
            // Who booked: the detail used to name the meeting type only.
            if (reunion.nom.isNotEmpty)
              Text(reunion.nom, style: TextStyle(fontSize: 15, color: gc.encre)),
            const SizedBox(height: 4),
            Text(
              '${DateFormat.yMMMMEEEEd(langueDesDates(context)).format(reunion.debut)} · '
              '${heureCourte(context, reunion.debut)}–${heureCourte(context, reunion.fin)}',
              style: TextStyle(color: gc.estompe, fontSize: 13),
            ),
            // Le fuseau de l'invité, pas le nôtre : c'est dans celui-là qu'il a lu
            // l'heure au moment de réserver, et c'est ce qu'il faut savoir avant de lui
            // proposer un report.
            Text(L.of(context).fuseauDeLInvite(reunion.fuseau),
                style: TextStyle(color: gc.estompe, fontSize: 12)),
            if (reunion.lieu != null) ...[
              const SizedBox(height: 12),
              _ligne(gc, Icons.place_outlined, reunion.lieu!),
            ],
            if (reunion.adresse != null)
              _ligne(gc, Icons.videocam_outlined, reunion.adresse!.toString()),
            if (reunion.courriel.isNotEmpty)
              _ligne(gc, Icons.mail_outline, reunion.courriel),
            if (widget.envoyerLeLien != null) ..._sectionDuLien(context, gc),
            if (reunion.reponses.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text(L.of(context).reponses,
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
              Text(L.of(context).notes,
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
                      title: Text(L.of(context).annulerCetteReunion),
                      content: Text(L.of(context).invitePrevenuParServeur),
                      actions: [
                        TextButton(
                            onPressed: () => Navigator.pop(c, false),
                            child: Text(L.of(context).retour)),
                        TextButton(
                            onPressed: () => Navigator.pop(c, true),
                            child: Text(L.of(context).annulerLaReunion)),
                      ],
                    ),
                  );
                  if (confirme != true) return;
                  if (context.mounted) Navigator.of(context).pop();
                  annuler!();
                },
                icon: Icon(Icons.event_busy, color: gc.danger),
                label: Text(L.of(context).annulerLaReunion, style: TextStyle(color: gc.danger)),
              ),
            ],
          ],
        ),
      ),
    );
  }

  List<Widget> _sectionDuLien(BuildContext context, Gc gc) {
    final l = L.of(context);
    return [
      const SizedBox(height: 12),
      if (!_formulaire)
        OutlinedButton.icon(
          key: const Key('reunion.lien'),
          icon: const Icon(Icons.videocam_outlined, size: 18),
          label: Text(reunion.adresse == null ? l.envoyerLeLienDeVisio : l.modifierOuRenvoyerLeLien),
          onPressed: () => setState(() {
            _formulaire = true;
            _message = null;
          }),
        )
      else ...[
        TextField(
          controller: _lien,
          autofocus: true,
          keyboardType: TextInputType.url,
          decoration: InputDecoration(labelText: l.lienDeVisio, hintText: 'https://'),
          onSubmitted: (_) => _envoyer(),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            FilledButton(
              onPressed: _envoi ? null : _envoyer,
              child: _envoi
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : Text(l.envoyer),
            ),
            const SizedBox(width: 8),
            TextButton(onPressed: () => setState(() => _formulaire = false), child: Text(l.annuler)),
          ],
        ),
      ],
      if (_message != null)
        Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Text(_message!,
              style: TextStyle(fontSize: 12, color: _messageOk ? gc.succes : gc.danger)),
        ),
    ];
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
