import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../services/reglages.dart';
import '../services/session.dart';
import '../theme.dart';
import '../l10n/generated/app_localisations.dart';

/// Les sondages de créneaux : ce que les invités ont voté, et le créneau qu'on retient.
class EcranDeSondages extends StatefulWidget {
  const EcranDeSondages({super.key, required this.session});

  final Session session;

  @override
  State<EcranDeSondages> createState() => _EcranDeSondagesState();
}

class _EcranDeSondagesState extends State<EcranDeSondages> {
  List<Sondage>? _sondages;
  String? _erreur;

  @override
  void initState() {
    super.initState();
    _recharger();
  }

  Reglages? get _service {
    final api = widget.session.api;
    return api == null ? null : Reglages(api: api);
  }

  Future<void> _recharger() async {
    final service = _service;
    if (service == null) return;
    setState(() => _erreur = null);
    try {
      final sondages = await service.sondages();
      if (mounted) setState(() => _sondages = sondages);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
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
        appBar: AppBar(title: Text(L.of(context).sondages)),
        body: RefreshIndicator(onRefresh: _recharger, child: _corps(gc)),
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
    final sondages = _sondages;
    if (sondages == null) return const Center(child: CircularProgressIndicator());
    if (sondages.isEmpty) {
      return ListView(
        padding: const EdgeInsets.all(20),
        children: [Text(L.of(context).aucunSondage, style: TextStyle(color: gc.estompe))],
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: sondages.length,
      separatorBuilder: (_, _) => Divider(height: 1, color: gc.bordure),
      itemBuilder: (_, i) {
        final sondage = sondages[i];
        return ListTile(
          title: Text(sondage.titre,
              style: TextStyle(color: sondage.ouvert ? gc.encre : gc.estompe)),
          subtitle: Text(
            '${L.of(context).creneauxEtVotes(sondage.nombreDOptions, sondage.nombreDeVotes)}'
            '${sondage.ouvert ? '' : ' · ${L.of(context).clos}'}',
            style: TextStyle(fontSize: 12, color: gc.estompe),
          ),
          trailing: const Icon(Icons.chevron_right),
          onTap: () async {
            await Navigator.of(context).push<void>(MaterialPageRoute(
              builder: (_) =>
                  EcranDUnSondage(session: widget.session, identifiant: sondage.id),
            ));
            await _recharger();
          },
        );
      },
    );
  }
}

/// Un sondage au complet : les créneaux, qui a voté, et de quoi trancher.
class EcranDUnSondage extends StatefulWidget {
  const EcranDUnSondage({super.key, required this.session, required this.identifiant});

  final Session session;
  final String identifiant;

  @override
  State<EcranDUnSondage> createState() => _EcranDUnSondageState();
}

class _EcranDUnSondageState extends State<EcranDUnSondage> {
  DetailDeSondage? _detail;
  String? _erreur;
  bool _occupe = false;

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
    try {
      final detail = await service.sondage(widget.identifiant);
      if (mounted) setState(() => _detail = detail);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    }
  }

  Future<void> _finaliser(OptionDeSondage option) async {
    final service = _service;
    if (service == null) return;
    final confirme = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(L.of(context).retenirCeCreneauQuestion),
        content: Text(
          L.of(context).sondageSeFermeEtEvenementCree(
              DateFormat.yMMMMEEEEd('fr_FR').add_Hm().format(option.debut)),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Annuler')),
          TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('Retenir')),
        ],
      ),
    );
    if (confirme != true) return;
    setState(() => _occupe = true);
    try {
      // Le serveur rend le sondage à jour : on le réutilise plutôt que de relire, sinon
      // deux appels donneraient deux vérités possibles entre-temps.
      final detail = await service.finaliser(widget.identifiant, option: option.id);
      if (mounted) setState(() => _detail = detail);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    } finally {
      if (mounted) setState(() => _occupe = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final detail = _detail;
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
        appBar: AppBar(
          title: Text(detail?.titre ?? 'Sondage'),
          actions: [
            if (detail != null && detail.ouvert)
              IconButton(
                icon: const Icon(Icons.delete_outline),
                tooltip: L.of(context).supprimerLeSondage,
                onPressed: _occupe ? null : _supprimer,
              ),
          ],
        ),
        body: detail == null
            ? Center(
                child: _erreur == null
                    ? const CircularProgressIndicator()
                    : Padding(
                        padding: const EdgeInsets.all(20),
                        child: Text(_erreur!, style: TextStyle(color: gc.danger)),
                      ),
              )
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  if (_erreur != null) ...[
                    Text(_erreur!, style: TextStyle(color: gc.danger, fontSize: 13)),
                    const SizedBox(height: 12),
                  ],
                  Text(
                    detail.ouvert
                        ? '${detail.duree} min · ${detail.votants.length} votants'
                        : '${detail.duree} min · clos',
                    style: TextStyle(color: gc.estompe, fontSize: 13),
                  ),
                  const SizedBox(height: 16),
                  _titre(gc, L.of(context).creneaux),
                  for (final option in detail.options) _creneau(gc, detail, option),
                  if (detail.votants.isNotEmpty) ...[
                    const SizedBox(height: 20),
                    _titre(gc, 'Votants'),
                    for (final votant in detail.votants)
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        dense: true,
                        title: Text(
                          votant.nom.isEmpty ? votant.courriel : votant.nom,
                          style: TextStyle(color: gc.encre),
                        ),
                        subtitle: Text(
                          // Le pluriel passe par ICU plutôt que par trois
                          // interpolations conditionnelles : « créneau/créneaux » et
                          // « retenu/retenus » ne s'accordent pas de la même façon
                          // d'une langue à l'autre, et l'anglais n'a pas de « x ».
                          L.of(context).creneauxRetenus(votant.options.length),
                          style: TextStyle(fontSize: 12, color: gc.estompe),
                        ),
                      ),
                  ],
                ],
              ),
    ),
    );
  }

  Widget _creneau(Gc gc, DetailDeSondage detail, OptionDeSondage option) {
    final retenu = detail.optionRetenue == option.id;
    // Le nombre de votes se lit d'un coup d'œil : c'est la seule chose qui décide.
    final maximum = detail.options.fold<int>(0, (m, o) => o.votes > m ? o.votes : m);
    final proportion = maximum == 0 ? 0.0 : option.votes / maximum;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: gc.surface2,
        borderRadius: BorderRadius.circular(Mesures.rayon),
        border: Border.all(color: retenu ? gc.accent : gc.bordure),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '${DateFormat.yMMMEd('fr_FR').format(option.debut)} · '
                  '${DateFormat.Hm().format(option.debut)}–${DateFormat.Hm().format(option.fin)}',
                  style: TextStyle(color: gc.encre, fontSize: 13),
                ),
              ),
              Text('${option.votes}',
                  style: TextStyle(color: gc.estompe, fontWeight: FontWeight.bold)),
            ],
          ),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: proportion,
              minHeight: 4,
              backgroundColor: gc.bordure,
              valueColor: AlwaysStoppedAnimation(gc.accent),
            ),
          ),
          if (retenu) ...[
            const SizedBox(height: 8),
            Row(
              children: [
                Icon(Icons.check_circle, size: 16, color: gc.succes),
                const SizedBox(width: 6),
                Text(L.of(context).creneauRetenu,
                    style: TextStyle(color: gc.succes, fontSize: 12)),
              ],
            ),
          ] else if (detail.ouvert) ...[
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: _occupe ? null : () => _finaliser(option),
                child: Text(L.of(context).retenirCeCreneau),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _supprimer() async {
    final service = _service;
    if (service == null) return;
    final confirme = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(L.of(context).supprimerCeSondage),
        content: Text(L.of(context).votesPerdus),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Annuler')),
          TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('Supprimer')),
        ],
      ),
    );
    if (confirme != true) return;
    try {
      await service.annulerLeSondage(widget.identifiant);
      if (mounted) Navigator.of(context).pop();
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    }
  }

  Widget _titre(Gc gc, String texte) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(
          texte.toUpperCase(),
          style: TextStyle(
              color: gc.estompe,
              fontSize: 11,
              fontWeight: FontWeight.w600,
              letterSpacing: 1.1),
        ),
      );
}
