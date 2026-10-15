import 'package:flutter/material.dart';

import '../l10n/generated/app_localisations.dart';
import '../services/api.dart' show ErreurAPI;
import '../services/erreurs.dart';
import '../services/types_de_rendez_vous.dart';
import '../theme.dart';

/// Create or edit a bookable event type — the Calendly side of the app.
///
/// The form edits the full detail fetched from the server, so settings made on the web
/// that this screen does not show (questions, hosts, team kinds) are sent back intact.
class EcranDeTypeDeRendezVous extends StatefulWidget {
  const EcranDeTypeDeRendezVous({super.key, required this.service, this.id});

  final TypesDeRendezVous service;

  /// `null` to create a new type.
  final String? id;

  @override
  State<EcranDeTypeDeRendezVous> createState() => _EcranDeTypeDeRendezVousState();
}

class _EcranDeTypeDeRendezVousState extends State<EcranDeTypeDeRendezVous> {
  final _titre = TextEditingController();
  final _description = TextEditingController();
  Map<String, dynamic> _detail = Map.of(TypesDeRendezVous.valeursParDefaut);
  bool _chargement = false;
  bool _occupe = false;
  String? _erreur;

  bool get _modification => widget.id != null;

  static const _durees = [15, 30, 45, 60, 90, 120];
  static const _preavis = [0, 60, 240, 1440, 2880];
  static const _fenetres = [7, 14, 30, 60, 90, 180];
  static const _tampons = [0, 5, 10, 15, 30];

  @override
  void initState() {
    super.initState();
    if (_modification) _charger();
  }

  @override
  void dispose() {
    _titre.dispose();
    _description.dispose();
    super.dispose();
  }

  Future<void> _charger() async {
    setState(() => _chargement = true);
    try {
      final detail = await widget.service.detail(widget.id!);
      if (!mounted) return;
      setState(() {
        _detail = detail;
        _titre.text = '${detail['title'] ?? ''}';
        _description.text = '${detail['description'] ?? ''}';
      });
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, L.of(context)));
    } finally {
      if (mounted) setState(() => _chargement = false);
    }
  }

  int _entier(String cle) => (_detail[cle] as num?)?.toInt() ?? 0;

  void _poser(String cle, Object? valeur) => setState(() => _detail[cle] = valeur);

  Future<void> _enregistrer() async {
    setState(() {
      _occupe = true;
      _erreur = null;
    });
    final champs = {
      ..._detail,
      'title': _titre.text.trim(),
      'description': _description.text.trim().isEmpty ? null : _description.text.trim(),
      // Slots follow the duration, as on the web: a 45-minute type offered every 15
      // minutes floods the booking page.
      'slot_interval_min': _entier('duration_min'),
    };
    try {
      if (_modification) {
        await widget.service.enregistrer(widget.id!, champs);
      } else {
        await widget.service.creer(champs);
      }
      if (mounted) Navigator.of(context).pop(true);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, L.of(context)));
    } finally {
      if (mounted) setState(() => _occupe = false);
    }
  }

  Future<void> _supprimer() async {
    final l = L.of(context);
    final confirme = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(l.supprimerCeType),
        content: Text(l.supprimerCeTypeExplication),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: Text(l.annuler)),
          TextButton(onPressed: () => Navigator.pop(c, true), child: Text(l.supprimer)),
        ],
      ),
    );
    if (confirme != true) return;
    try {
      await widget.service.supprimer(widget.id!);
      if (mounted) Navigator.of(context).pop(true);
    } on ErreurAPI catch (e) {
      // The server keeps types that have bookings; closing them is the way out.
      if (mounted) {
        setState(() => _erreur = e.statut == 409 ? l.typeAvecReservations : lisible(e, l));
      }
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, l));
    }
  }

  String _libelleDuLieu(L l, String lieu) => switch (lieu) {
        'google_meet' => 'Google Meet',
        'zoom' => 'Zoom',
        'kmeet' => 'kMeet (Infomaniak)',
        'ms_teams' => 'Microsoft Teams',
        'phone' => l.lieuTelephone,
        'in_person' => l.lieuEnPersonne,
        _ => l.lieuAutre,
      };

  String _duree(L l, int minutes) {
    if (minutes == 0) return l.aucun;
    if (minutes % 1440 == 0) return l.nJours(minutes ~/ 1440);
    if (minutes % 60 == 0) return l.nHeures(minutes ~/ 60);
    return '$minutes min';
  }

  Widget _choix<T>(String titre, List<T> valeurs, T actuelle, String Function(T) libelle,
      ValueChanged<T> choisir) {
    final gc = Gc.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(titre, style: TextStyle(fontSize: 12, color: gc.estompe)),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final v in {...valeurs, actuelle})
                ChoiceChip(
                  label: Text(libelle(v)),
                  selected: v == actuelle,
                  onSelected: (_) => choisir(v),
                ),
            ],
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = L.of(context);
    final gc = Gc.of(context);
    return FondGhost(
      child: Scaffold(
        appBar: AppBar(
          title: Text(_modification ? l.modifierLeType : l.nouveauType),
          actions: [
            if (_modification)
              IconButton(
                icon: const Icon(Icons.delete_outline),
                tooltip: l.supprimer,
                onPressed: _occupe ? null : _supprimer,
              ),
            TextButton(
              onPressed: _occupe || _chargement || _titre.text.trim().isEmpty ? null : _enregistrer,
              child: Text(l.enregistrer),
            ),
          ],
        ),
        body: _chargement
            ? const Center(child: CircularProgressIndicator())
            : ContenuBorne(
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(20, 12, 20, 40),
                  children: [
                    if (_erreur != null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Text(_erreur!, style: TextStyle(color: gc.danger)),
                      ),
                    TextField(
                      key: const Key('type.titre'),
                      controller: _titre,
                      onChanged: (_) => setState(() {}),
                      decoration: InputDecoration(labelText: l.titre),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _description,
                      maxLines: 3,
                      decoration: InputDecoration(labelText: l.descriptionPublique),
                    ),
                    _choix<int>(l.duree, _durees, _entier('duration_min'), (m) => _duree(l, m),
                        (m) => _poser('duration_min', m)),
                    _choix<String>(
                        l.lieu,
                        TypesDeRendezVous.lieux,
                        '${_detail['location_type'] ?? 'google_meet'}',
                        (v) => _libelleDuLieu(l, v),
                        (v) => _poser('location_type', v)),
                    _choix<int>(l.preavisMinimum, _preavis, _entier('min_notice_min'),
                        (m) => _duree(l, m), (m) => _poser('min_notice_min', m)),
                    _choix<int>(l.reservableSur, _fenetres, _entier('date_window_days'),
                        (j) => l.nJours(j), (j) => _poser('date_window_days', j)),
                    _choix<int>(l.tamponAvant, _tampons, _entier('buffer_before_min'),
                        (m) => _duree(l, m), (m) => _poser('buffer_before_min', m)),
                    _choix<int>(l.tamponApres, _tampons, _entier('buffer_after_min'),
                        (m) => _duree(l, m), (m) => _poser('buffer_after_min', m)),
                    const SizedBox(height: 12),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(l.ouvertALaReservation),
                      value: _detail['active'] != false,
                      onChanged: (v) => _poser('active', v),
                    ),
                    Text(l.typeDisponibilitesDepuisHoraire,
                        style: TextStyle(fontSize: 12, color: gc.estompe)),
                  ],
                ),
              ),
      ),
    );
  }
}
