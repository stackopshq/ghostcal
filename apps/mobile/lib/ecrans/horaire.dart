import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../l10n/generated/app_localisations.dart';
import '../outils/dates.dart';
import '../services/agenda.dart' show Agenda;
import '../services/erreurs.dart';
import '../services/reglages.dart';
import '../theme.dart';
import 'agenda_vues.dart' show heureCourte;
import 'choix_du_fuseau.dart';

/// Edit when people can book you: weekly ranges per day, in a time zone.
///
/// Edits start from the server's full schedule, so date exceptions (overrides) set on
/// the web are sent back unchanged.
class EcranDHoraire extends StatefulWidget {
  const EcranDHoraire({super.key, required this.service, this.id});

  final Reglages service;

  /// `null` to create the first schedule (office hours by default).
  final String? id;

  @override
  State<EcranDHoraire> createState() => _EcranDHoraireState();
}

typedef _Plage = ({int jour, TimeOfDay debut, TimeOfDay fin});

class _EcranDHoraireState extends State<EcranDHoraire> {
  final _nom = TextEditingController();
  Map<String, dynamic> _detail = {};
  String _fuseau = 'UTC';
  List<_Plage> _plages = [];
  bool _chargement = false;
  bool _occupe = false;
  String? _erreur;

  @override
  void initState() {
    super.initState();
    if (widget.id == null) {
      _plages = [
        for (var j = 0; j < 5; j++)
          (jour: j, debut: const TimeOfDay(hour: 9, minute: 0), fin: const TimeOfDay(hour: 17, minute: 0)),
      ];
      Agenda.fuseauCourant().then((f) {
        if (mounted) setState(() => _fuseau = f);
      });
    } else {
      _charger();
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (widget.id == null && _nom.text.isEmpty) _nom.text = L.of(context).heuresDeBureau;
  }

  @override
  void dispose() {
    _nom.dispose();
    super.dispose();
  }

  static TimeOfDay _heure(String brut) {
    final parties = brut.split(':');
    return TimeOfDay(hour: int.parse(parties[0]), minute: int.parse(parties[1]));
  }

  static String _versServeur(TimeOfDay t) =>
      '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';

  static int _minutes(TimeOfDay t) => t.hour * 60 + t.minute;

  Future<void> _charger() async {
    setState(() => _chargement = true);
    try {
      final detail = await widget.service.horaire(widget.id!);
      if (!mounted) return;
      setState(() {
        _detail = detail;
        _nom.text = '${detail['name'] ?? ''}';
        _fuseau = '${detail['timezone'] ?? 'UTC'}';
        _plages = [
          for (final r in (detail['rules'] as List? ?? const []).whereType<Map<String, dynamic>>())
            (
              jour: (r['weekday'] as num).toInt(),
              debut: _heure('${r['start']}'),
              fin: _heure('${r['end']}'),
            ),
        ];
      });
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, L.of(context)));
    } finally {
      if (mounted) setState(() => _chargement = false);
    }
  }

  Future<void> _enregistrer() async {
    final l = L.of(context);
    if (_plages.any((p) => _minutes(p.fin) <= _minutes(p.debut))) {
      setState(() => _erreur = l.finAvantDebut);
      return;
    }
    setState(() {
      _occupe = true;
      _erreur = null;
    });
    final corps = {
      ..._detail,
      'name': _nom.text.trim(),
      'timezone': _fuseau,
      'rules': [
        for (final p in _plages)
          {'weekday': p.jour, 'start': _versServeur(p.debut), 'end': _versServeur(p.fin)},
      ],
      'overrides': _detail['overrides'] ?? <dynamic>[],
    };
    try {
      if (widget.id == null) {
        await widget.service.creerHoraire(corps);
      } else {
        await widget.service.enregistrerHoraire(widget.id!, corps);
      }
      if (mounted) Navigator.of(context).pop(true);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, l));
    } finally {
      if (mounted) setState(() => _occupe = false);
    }
  }

  Future<void> _modifierLaPlage(int index) async {
    final plage = _plages[index];
    final debut = await showTimePicker(context: context, initialTime: plage.debut);
    if (debut == null || !mounted) return;
    final fin = await showTimePicker(context: context, initialTime: plage.fin);
    if (fin == null || !mounted) return;
    setState(() => _plages[index] = (jour: plage.jour, debut: debut, fin: fin));
  }

  void _ajouter(int jour) {
    final dujour = _plages.where((p) => p.jour == jour).toList();
    final debut = dujour.isEmpty
        ? const TimeOfDay(hour: 9, minute: 0)
        : TimeOfDay(hour: (dujour.last.fin.hour + 1).clamp(0, 22), minute: 0);
    final fin = TimeOfDay(hour: (debut.hour + (dujour.isEmpty ? 8 : 1)).clamp(1, 23), minute: 0);
    setState(() => _plages.add((jour: jour, debut: debut, fin: fin)));
  }

  @override
  Widget build(BuildContext context) {
    final l = L.of(context);
    final gc = Gc.of(context);
    final langue = langueDesDates(context);
    // Days in the locale's order; the server counts from Monday = 0.
    final premier = MaterialLocalizations.of(context).firstDayOfWeekIndex; // 0 = Sunday
    final ordre = [for (var i = 0; i < 7; i++) (premier + 6 + i) % 7];
    return FondGhost(
      child: Scaffold(
        appBar: AppBar(
          title: Text(l.disponibilites),
          actions: [
            TextButton(
              onPressed: _occupe || _chargement || _nom.text.trim().isEmpty ? null : _enregistrer,
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
                      controller: _nom,
                      onChanged: (_) => setState(() {}),
                      decoration: InputDecoration(labelText: l.nom),
                    ),
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.public),
                      title: Text(l.fuseauHoraire),
                      subtitle: Text(_fuseau.replaceAll('_', ' ')),
                      trailing: const Icon(Icons.expand_more),
                      onTap: () async {
                        final choisi = await showModalBottomSheet<String>(
                          context: context,
                          isScrollControlled: true,
                          builder: (_) => const ChoixDuFuseau(),
                        );
                        if (choisi != null) setState(() => _fuseau = choisi);
                      },
                    ),
                    const Divider(),
                    for (final jour in ordre) _jour(context, gc, l, langue, jour),
                  ],
                ),
              ),
      ),
    );
  }

  Widget _jour(BuildContext context, Gc gc, L l, String langue, int jour) {
    final indices = [
      for (var i = 0; i < _plages.length; i++)
        if (_plages[i].jour == jour) i,
    ];
    final nom = toBeginningOfSentenceCase(
        DateFormat.EEEE(langue).format(DateTime(2024, 1, 1 + jour)));
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text(nom, style: TextStyle(color: gc.encre, fontSize: 15))),
              Switch(
                key: Key('horaire.jour.$jour'),
                value: indices.isNotEmpty,
                onChanged: (actif) => actif
                    ? _ajouter(jour)
                    : setState(() => _plages.removeWhere((p) => p.jour == jour)),
              ),
            ],
          ),
          if (indices.isEmpty)
            Text(l.indisponible, style: TextStyle(color: gc.estompe, fontSize: 12))
          else
            Wrap(
              spacing: 6,
              runSpacing: 6,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                for (final i in indices)
                  InputChip(
                    label: Text(
                        '${heureCourte(context, DateTime(2000, 1, 1, _plages[i].debut.hour, _plages[i].debut.minute))}'
                        ' – '
                        '${heureCourte(context, DateTime(2000, 1, 1, _plages[i].fin.hour, _plages[i].fin.minute))}'),
                    onPressed: () => _modifierLaPlage(i),
                    onDeleted: () => setState(() => _plages.removeAt(i)),
                  ),
                IconButton(
                  icon: const Icon(Icons.add_circle_outline),
                  tooltip: l.ajouterUnePlage,
                  onPressed: () => _ajouter(jour),
                ),
              ],
            ),
        ],
      ),
    );
  }
}
