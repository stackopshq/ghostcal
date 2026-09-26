import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/session.dart';
import '../services/types_de_rendez_vous.dart';
import '../theme.dart';
import '../l10n/generated/app_localisations.dart';

/// Ce qu'on propose à réserver : vérifier ce qui est ouvert, partager un lien, couper un
/// créneau qu'on ne veut plus.
///
/// Volontairement partiel. Créer un type demande une quinzaine de réglages qui se règlent
/// bien à un clavier et mal à un pouce ; proposer un formulaire incomplet ferait créer des
/// types à moitié configurés.
class EcranDeTypesDeRendezVous extends StatefulWidget {
  const EcranDeTypesDeRendezVous({super.key, required this.session});

  final Session session;

  @override
  State<EcranDeTypesDeRendezVous> createState() => _EcranDeTypesDeRendezVousState();
}

class _EcranDeTypesDeRendezVousState extends State<EcranDeTypesDeRendezVous> {
  List<TypeDeRendezVous>? _types;
  String? _erreur;

  @override
  void initState() {
    super.initState();
    _recharger();
  }

  TypesDeRendezVous? get _service {
    final api = widget.session.api;
    return api == null ? null : TypesDeRendezVous(api: api);
  }

  Future<void> _recharger() async {
    final service = _service;
    if (service == null) return;
    setState(() => _erreur = null);
    try {
      final types = await service.lister();
      if (mounted) setState(() => _types = types);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    }
  }

  Future<void> _basculer(TypeDeRendezVous type) async {
    final service = _service;
    if (service == null) return;
    try {
      await service.basculer(type, actif: !type.actif);
      await _recharger();
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(L.of(context).rendezVous)),
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
    final types = _types;
    if (types == null) return const Center(child: CircularProgressIndicator());
    if (types.isEmpty) {
      return ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(L.of(context).aucunTypeDeRendezVous, style: TextStyle(color: gc.estompe)),
          const SizedBox(height: 8),
          Text(
            L.of(context).typesCreesDepuisLeWeb,
            style: TextStyle(color: gc.estompe, fontSize: 12),
          ),
        ],
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: types.length,
      separatorBuilder: (_, _) => Divider(height: 1, color: gc.bordure),
      itemBuilder: (_, i) => _ligne(gc, types[i]),
    );
  }

  Widget _ligne(Gc gc, TypeDeRendezVous type) {
    final base = widget.session.api?.base;
    final lien =
        base == null ? null : TypesDeRendezVous.lienPublic(type, serveur: base);
    return ListTile(
      title: Text(
        type.titre,
        style: TextStyle(color: type.actif ? gc.encre : gc.estompe),
      ),
      subtitle: Text(
        [
          '${type.duree} min',
          if (!type.actif) L.of(context).ferme,
        ].join(' · '),
        style: TextStyle(fontSize: 12, color: type.actif ? gc.estompe : gc.danger),
      ),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (lien != null)
            IconButton(
              icon: const Icon(Icons.link),
              tooltip: L.of(context).copierLeLienDeReservation,
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: lien.toString()));
                // `mounted` de l'État, pas du contexte : c'est celui-là qui garantit que
                // l'écran existe encore après l'attente.
                if (!mounted) return;
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(L.of(context).lienCopie(lien.toString()))),
                );
              },
            ),
          Switch(
            value: type.actif,
            onChanged: (_) => _basculer(type),
          ),
        ],
      ),
    );
  }
}
