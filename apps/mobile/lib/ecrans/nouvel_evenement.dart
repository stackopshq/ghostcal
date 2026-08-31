import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../services/agenda.dart';
import '../services/session.dart';
import '../theme.dart';

/// Créer ou modifier un événement.
///
/// Le même écran pour les deux : les champs sont identiques, et deux écrans jumeaux
/// divergeraient à la première correction faite d'un seul côté.
class EcranDeNouvelEvenement extends StatefulWidget {
  const EcranDeNouvelEvenement({
    super.key,
    required this.session,
    required this.calendriers,
    required this.jour,
    this.evenement,
  });

  final Session session;
  final List<Calendrier> calendriers;
  final DateTime jour;

  /// Nul à la création. Renseigné, l'écran charge le détail et enregistre par `PUT`.
  final String? evenement;

  @override
  State<EcranDeNouvelEvenement> createState() => _EcranDeNouvelEvenementState();
}

class _EcranDeNouvelEvenementState extends State<EcranDeNouvelEvenement> {
  final _titre = TextEditingController();
  final _description = TextEditingController();
  final _lieu = TextEditingController();

  late DateTime _debut;
  late DateTime _fin;
  bool _journeeEntiere = false;
  String? _calendrier;
  String? _fuseau;
  bool _occupe = false;
  bool _chargement = false;
  String? _erreur;

  bool get _modification => widget.evenement != null;

  @override
  void initState() {
    super.initState();
    final j = widget.jour;
    _debut = DateTime(j.year, j.month, j.day, 9);
    _fin = _debut.add(const Duration(hours: 1));
    _calendrier = widget.calendriers
        .where((c) => c.parDefaut)
        .followedBy(widget.calendriers)
        .map((c) => c.id)
        .firstOrNull;
    if (_modification) _charger();
  }

  @override
  void dispose() {
    _titre.dispose();
    _description.dispose();
    _lieu.dispose();
    super.dispose();
  }

  Agenda? get _agenda {
    final api = widget.session.api;
    final auth = widget.session.auth;
    if (api == null || auth == null) return null;
    return Agenda(api: api, auth: auth);
  }

  /// Charge le détail avant de laisser modifier.
  ///
  /// L'agenda ne donne que ce qu'il faut pour afficher ; enregistrer demande le reste — le
  /// calendrier, la description, et le fuseau **dans lequel l'événement a été posé**. Le
  /// remplacer par celui de l'appareil déplacerait un rendez-vous pris dans un autre pays.
  Future<void> _charger() async {
    final agenda = _agenda;
    final organisation = widget.session.organisation;
    if (agenda == null || organisation == null) return;
    setState(() => _chargement = true);
    try {
      final detail =
          await agenda.evenement(widget.evenement!, organisation: organisation);
      if (!mounted) return;
      setState(() {
        _debut = detail.debut;
        _fin = detail.fin;
        _journeeEntiere = detail.journeeEntiere;
        _calendrier = detail.calendrier;
        _fuseau = detail.fuseau;
        _titre.text = detail.contenu?.title ?? '';
        _description.text = detail.contenu?.description ?? '';
        _lieu.text = detail.contenu?.location ?? '';
        // Un contenu scellé qu'on n'a pas su ouvrir : enregistrer écraserait un titre
        // qu'on n'a jamais lu. On le dit, et on empêche.
        if (detail.contenu == null) {
          _erreur = "Le contenu de cet événement n'a pas pu être déchiffré. "
              "L'enregistrer remplacerait un titre que vous n'avez pas pu lire.";
        }
      });
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    } finally {
      if (mounted) setState(() => _chargement = false);
    }
  }

  bool get _illisible =>
      _modification && _erreur != null && _titre.text.isEmpty && !_chargement;

  Future<void> _enregistrer() async {
    final agenda = _agenda;
    final organisation = widget.session.organisation;
    final calendrier = _calendrier;
    if (agenda == null || organisation == null || calendrier == null) return;
    if (_fin.isBefore(_debut)) {
      setState(() => _erreur = "La fin est avant le début.");
      return;
    }
    setState(() {
      _occupe = true;
      _erreur = null;
    });
    try {
      if (_modification) {
        await agenda.modifierUnEvenement(
          widget.evenement!,
          titre: _titre.text,
          description: _description.text,
          lieu: _lieu.text,
          debut: _debut,
          fin: _fin,
          journeeEntiere: _journeeEntiere,
          fuseau: _fuseau ?? await Agenda.fuseauCourant(),
          calendrier: calendrier,
          organisation: organisation,
        );
      } else {
        await agenda.creerUnEvenement(
          titre: _titre.text,
          description: _description.text,
          lieu: _lieu.text,
          debut: _debut,
          fin: _fin,
          journeeEntiere: _journeeEntiere,
          calendrier: calendrier,
          organisation: organisation,
        );
      }
      if (mounted) Navigator.of(context).pop(true);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    } finally {
      if (mounted) setState(() => _occupe = false);
    }
  }

  Future<void> _supprimer() async {
    final agenda = _agenda;
    if (agenda == null) return;
    final confirme = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Supprimer cet événement ?'),
        content: const Text('Il disparaîtra pour tous les participants.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(c, false), child: const Text('Annuler')),
          TextButton(
            onPressed: () => Navigator.pop(c, true),
            child: const Text('Supprimer'),
          ),
        ],
      ),
    );
    if (confirme != true) return;
    setState(() => _occupe = true);
    try {
      await agenda.supprimerUnEvenement(widget.evenement!);
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
    return Scaffold(
      appBar: AppBar(
        title: Text(_modification ? "Modifier l'événement" : 'Nouvel événement'),
        actions: [
          if (_modification)
            IconButton(
              icon: const Icon(Icons.delete_outline),
              tooltip: 'Supprimer',
              onPressed: _occupe ? null : _supprimer,
            ),
          TextButton(
            onPressed: _occupe || _illisible ? null : _enregistrer,
            child: const Text('Enregistrer'),
          ),
        ],
      ),
      body: _chargement
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                if (_erreur != null) ...[
                  Text(_erreur!, style: TextStyle(color: gc.danger, fontSize: 13)),
                  const SizedBox(height: 14),
                ],
                TextField(
                  controller: _titre,
                  decoration: const InputDecoration(labelText: 'Titre'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _lieu,
                  decoration: const InputDecoration(labelText: 'Lieu'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _description,
                  maxLines: 4,
                  decoration: const InputDecoration(labelText: 'Description'),
                ),
                const SizedBox(height: 8),
                SwitchListTile(
                  title: const Text('Journée entière'),
                  value: _journeeEntiere,
                  onChanged: (v) => setState(() => _journeeEntiere = v),
                ),
                _dateEtHeure(gc, 'Début', _debut, (d) => setState(() {
                      final duree = _fin.difference(_debut);
                      _debut = d;
                      // La durée suit le début : déplacer un rendez-vous d'une heure ne
                      // doit pas l'allonger silencieusement jusqu'à l'ancienne fin.
                      _fin = d.add(duree);
                    })),
                _dateEtHeure(gc, 'Fin', _fin, (d) => setState(() => _fin = d)),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue: _calendrier,
                  decoration: const InputDecoration(labelText: 'Calendrier'),
                  items: [
                    for (final c in widget.calendriers)
                      DropdownMenuItem(value: c.id, child: Text(c.nom)),
                  ],
                  onChanged: (v) => setState(() => _calendrier = v),
                ),
                const SizedBox(height: 16),
                Text(
                  'Le titre, le lieu et la description sont chiffrés sur cet appareil. '
                  'Les heures partent en clair : sans elles, le serveur ne pourrait ni '
                  'répondre « occupé » à un lien de réservation, ni envoyer de rappel.',
                  style: TextStyle(color: gc.estompe, fontSize: 12),
                ),
              ],
            ),
    );
  }

  Widget _dateEtHeure(Gc gc, String titre, DateTime valeur, ValueChanged<DateTime> poser) =>
      ListTile(
        contentPadding: EdgeInsets.zero,
        title: Text(titre, style: TextStyle(color: gc.estompe, fontSize: 12)),
        subtitle: Text(
          _journeeEntiere
              ? DateFormat.yMMMMd('fr_FR').format(valeur)
              : DateFormat.yMMMMd('fr_FR').add_Hm().format(valeur),
          style: TextStyle(color: gc.encre),
        ),
        trailing: const Icon(Icons.edit_calendar_outlined),
        onTap: () async {
          final date = await showDatePicker(
            context: context,
            initialDate: valeur,
            firstDate: DateTime(2000),
            lastDate: DateTime(2100),
          );
          if (date == null || !mounted) return;
          if (_journeeEntiere) {
            poser(DateTime(date.year, date.month, date.day, valeur.hour, valeur.minute));
            return;
          }
          final heure = await showTimePicker(
            // ignore: use_build_context_synchronously
            context: context,
            initialTime: TimeOfDay.fromDateTime(valeur),
          );
          if (heure == null) return;
          poser(DateTime(date.year, date.month, date.day, heure.hour, heure.minute));
        },
      );
}
