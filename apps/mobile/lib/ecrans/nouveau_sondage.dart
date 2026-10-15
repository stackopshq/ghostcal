import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../l10n/generated/app_localisations.dart';
import '../outils/dates.dart';
import '../services/erreurs.dart';
import '../services/reglages.dart';
import '../services/types_de_rendez_vous.dart';
import '../theme.dart';
import 'agenda_vues.dart' show heureCourte;

/// Create a date poll: a title, a duration, and the slots people vote on.
class EcranDeNouveauSondage extends StatefulWidget {
  const EcranDeNouveauSondage({super.key, required this.service});

  final Reglages service;

  @override
  State<EcranDeNouveauSondage> createState() => _EcranDeNouveauSondageState();
}

class _EcranDeNouveauSondageState extends State<EcranDeNouveauSondage> {
  final _titre = TextEditingController();
  int _duree = 60;
  String _lieu = 'google_meet';
  final List<DateTime> _creneaux = [];
  bool _occupe = false;
  String? _erreur;

  static const _durees = [30, 45, 60, 90, 120];

  @override
  void dispose() {
    _titre.dispose();
    super.dispose();
  }

  Future<void> _ajouter() async {
    final base = _creneaux.isEmpty
        ? DateTime.now().add(const Duration(days: 1))
        : _creneaux.last.add(const Duration(days: 1));
    final date = await showDatePicker(
      context: context,
      initialDate: base,
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (date == null || !mounted) return;
    final heure = await showTimePicker(
      context: context,
      initialTime: _creneaux.isEmpty
          ? const TimeOfDay(hour: 10, minute: 0)
          : TimeOfDay.fromDateTime(_creneaux.last),
    );
    if (heure == null || !mounted) return;
    setState(() {
      _creneaux
        ..add(DateTime(date.year, date.month, date.day, heure.hour, heure.minute))
        ..sort();
    });
  }

  Future<void> _creer() async {
    final l = L.of(context);
    if (_creneaux.length < 2) {
      setState(() => _erreur = l.auMoinsDeuxCreneaux);
      return;
    }
    setState(() {
      _occupe = true;
      _erreur = null;
    });
    try {
      final sondage = await widget.service.creerUnSondage(
        titre: _titre.text.trim(),
        duree: _duree,
        lieu: _lieu,
        creneaux: _creneaux,
      );
      if (mounted) Navigator.of(context).pop(sondage);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, l));
    } finally {
      if (mounted) setState(() => _occupe = false);
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

  @override
  Widget build(BuildContext context) {
    final l = L.of(context);
    final gc = Gc.of(context);
    final langue = langueDesDates(context);
    return FondGhost(
      child: Scaffold(
        appBar: AppBar(
          title: Text(l.nouveauSondage),
          actions: [
            TextButton(
              onPressed: _occupe || _titre.text.trim().isEmpty ? null : _creer,
              child: Text(l.creer),
            ),
          ],
        ),
        body: ContenuBorne(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 40),
            children: [
              if (_erreur != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(_erreur!, style: TextStyle(color: gc.danger)),
                ),
              TextField(
                controller: _titre,
                autofocus: true,
                onChanged: (_) => setState(() {}),
                decoration: InputDecoration(labelText: l.titre),
              ),
              const SizedBox(height: 16),
              Text(l.duree, style: TextStyle(fontSize: 12, color: gc.estompe)),
              const SizedBox(height: 6),
              Wrap(spacing: 6, children: [
                for (final d in _durees)
                  ChoiceChip(
                    label: Text('$d min'),
                    selected: d == _duree,
                    onSelected: (_) => setState(() => _duree = d),
                  ),
              ]),
              const SizedBox(height: 16),
              Text(l.lieu, style: TextStyle(fontSize: 12, color: gc.estompe)),
              const SizedBox(height: 6),
              Wrap(spacing: 6, runSpacing: 6, children: [
                for (final v in TypesDeRendezVous.lieux)
                  ChoiceChip(
                    label: Text(_libelleDuLieu(l, v)),
                    selected: v == _lieu,
                    onSelected: (_) => setState(() => _lieu = v),
                  ),
              ]),
              const SizedBox(height: 20),
              Text(l.creneauxProposes.toUpperCase(),
                  style: TextStyle(
                      fontSize: 11, color: gc.estompe, fontWeight: FontWeight.w600, letterSpacing: 1.1)),
              for (var i = 0; i < _creneaux.length; i++)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.event_available_outlined),
                  title: Text(DateFormat.yMMMMEEEEd(langue).format(_creneaux[i])),
                  subtitle: Text(
                      '${heureCourte(context, _creneaux[i])} – ${heureCourte(context, _creneaux[i].add(Duration(minutes: _duree)))}'),
                  trailing: IconButton(
                    icon: const Icon(Icons.close),
                    tooltip: l.supprimer,
                    onPressed: () => setState(() => _creneaux.removeAt(i)),
                  ),
                ),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                key: const Key('sondage.ajouter'),
                icon: const Icon(Icons.add),
                label: Text(l.ajouterUnCreneau),
                onPressed: _creneaux.length >= 25 ? null : _ajouter,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
