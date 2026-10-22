import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../services/erreurs.dart';
import '../services/agenda.dart';
import '../services/session.dart';
import '../outils/dates.dart';
import '../outils/saisie_rapide.dart';
import '../theme.dart';
import '../l10n/generated/app_localisations.dart';

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
    this.debut,
    this.occurrence,
    this.surFin,
  });

  /// Comment l'écran se referme, quand il n'est **pas** une route.
  ///
  /// Sur une fenêtre large l'agenda le loge dans un panneau à côté de la grille, et il
  /// n'y a alors aucune route à dépiler : `Navigator.pop` y retirerait l'agenda
  /// lui-même. Le drapeau dit si quelque chose a changé, donc s'il faut recharger.
  final ValueChanged<bool>? surFin;

  /// The start of the occurrence tapped in the agenda, for a series: the one "delete
  /// this occurrence" removes.
  final DateTime? occurrence;

  /// The start picked by tapping an empty slot in the day or week grid; 09:00 on
  /// [jour] otherwise.
  final DateTime? debut;

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

  /// The event as loaded, kept for what the form does not show (recurrence, exceptions,
  /// reminder) and sent back with it.
  DetailDEvenement? _detail;

  bool get _modification => widget.evenement != null;

  @override
  void initState() {
    super.initState();
    final j = widget.jour;
    _debut = widget.debut ?? DateTime(j.year, j.month, j.day, 9);
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
      final detail = await agenda.evenement(
        widget.evenement!,
        organisation: organisation,
      );
      if (!mounted) return;
      setState(() {
        _detail = detail;
        _debut = detail.debut;
        // The form shows the last day included; the server stores an exclusive end.
        _fin = detail.journeeEntiere
            ? Agenda.dernierJourInclus(detail.debut, detail.fin)
            : detail.fin;
        _journeeEntiere = detail.journeeEntiere;
        _calendrier = detail.calendrier;
        _fuseau = detail.fuseau;
        _titre.text = detail.contenu?.title ?? '';
        _description.text = detail.contenu?.description ?? '';
        _lieu.text = detail.contenu?.location ?? '';
        // Un contenu scellé qu'on n'a pas su ouvrir : enregistrer écraserait un titre
        // qu'on n'a jamais lu. On le dit, et on empêche.
        if (detail.contenu == null) {
          _erreur = L.of(context).contenuNonDechiffre;
        }
      });
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, L.of(context)));
    } finally {
      if (mounted) setState(() => _chargement = false);
    }
  }

  /// Fills the form from a quick-entry sentence. What was not recognised is left
  /// as it was, so the sentence never erases a date the user picked by hand.
  void _appliquerLaSaisie(String texte) {
    final r = analyserLaSaisie(texte);
    setState(() {
      _titre.text = r.titre;
      if (r.lieu.isNotEmpty) _lieu.text = r.lieu;
      final debut = r.debut;
      final fin = r.fin;
      if (debut != null && fin != null) {
        _journeeEntiere = r.journeeEntiere;
        _debut = debut;
        _fin = r.journeeEntiere ? debut : fin;
      }
    });
  }

  bool get _illisible =>
      _modification && _erreur != null && _titre.text.isEmpty && !_chargement;

  Future<void> _enregistrer() async {
    final agenda = _agenda;
    final organisation = widget.session.organisation;
    final calendrier = _calendrier;
    if (agenda == null || organisation == null || calendrier == null) return;
    if (_fin.isBefore(_debut)) {
      setState(() => _erreur = L.of(context).finAvantDebut);
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
          rrule: _detail?.rrule,
          exdates: _detail?.exdates ?? const [],
          rappelMinutes: _detail?.rappelMinutes,
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
      _terminer(true);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, L.of(context)));
    } finally {
      if (mounted) setState(() => _occupe = false);
    }
  }

  Future<void> _supprimer() async {
    final agenda = _agenda;
    if (agenda == null) return;
    final detail = _detail;
    final l = L.of(context);
    // A series offers both: the occurrence tapped in the agenda, or all of it.
    final serie = detail != null && detail.repete;
    final choix = await showDialog<_Suppression>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(l.supprimerCetEvenement),
        content: Text(serie ? l.evenementQuiSeRepete : l.disparaitraPourTous),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c), child: Text(l.annuler)),
          if (serie)
            TextButton(
              key: const Key('evenement.supprimer.occurrence'),
              onPressed: () => Navigator.pop(c, _Suppression.occurrence),
              child: Text(l.cetteOccurrence),
            ),
          TextButton(
            key: const Key('evenement.supprimer.tout'),
            onPressed: () => Navigator.pop(c, _Suppression.tout),
            child: Text(serie ? l.touteLaSerie : l.supprimer),
          ),
        ],
      ),
    );
    if (choix == null) return;
    setState(() => _occupe = true);
    try {
      if (choix == _Suppression.occurrence) {
        await agenda.supprimerUneOccurrence(
          detail!,
          widget.occurrence ?? widget.jour,
        );
      } else {
        await agenda.supprimerUnEvenement(widget.evenement!);
      }
      _terminer(true);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, L.of(context)));
    } finally {
      if (mounted) setState(() => _occupe = false);
    }
  }

  /// Referme, par la route ou par le panneau selon la façon dont l'écran est monté.
  void _terminer(bool modifie) {
    if (!mounted) return;
    final surFin = widget.surFin;
    if (surFin != null) {
      surFin(modifie);
      return;
    }
    Navigator.of(context).pop(modifie);
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
        appBar: AppBar(
          automaticallyImplyLeading: widget.surFin == null,
          leading: widget.surFin == null
              ? null
              : IconButton(
                  icon: const Icon(Icons.close),
                  tooltip: L.of(context).annuler,
                  onPressed: () => _terminer(false),
                ),
          title: Text(
            _modification
                ? L.of(context).modifierLEvenement
                : L.of(context).nouvelEvenement,
          ),
          actions: [
            if (_modification)
              IconButton(
                icon: const Icon(Icons.delete_outline),
                tooltip: L.of(context).supprimer,
                onPressed: _occupe ? null : _supprimer,
              ),
            TextButton(
              onPressed: _occupe || _illisible ? null : _enregistrer,
              child: Text(L.of(context).enregistrer),
            ),
          ],
        ),
        body: ContenuBorne(
          child: _chargement
              ? const Center(child: CircularProgressIndicator())
              : ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    if (_erreur != null) ...[
                      Text(
                        _erreur!,
                        style: TextStyle(color: gc.danger, fontSize: 13),
                      ),
                      const SizedBox(height: 14),
                    ],
                    if (_detail?.repete ?? false) ...[
                      Text(
                        L.of(context).modifierLaSerie,
                        key: const Key('evenement.serie'),
                        style: TextStyle(color: gc.estompe, fontSize: 13),
                      ),
                      const SizedBox(height: 14),
                    ],
                    // Fantastical-style quick entry, creation only: typing a sentence
                    // fills the form below, which stays editable.
                    if (!_modification) ...[
                      TextField(
                        key: const Key('saisie.rapide'),
                        autofocus: true,
                        textCapitalization: TextCapitalization.sentences,
                        decoration: InputDecoration(
                          prefixIcon: const Icon(Icons.auto_awesome),
                          labelText: L.of(context).saisieRapide,
                          hintText: L.of(context).saisieRapideExemple,
                        ),
                        onChanged: _appliquerLaSaisie,
                      ),
                      const SizedBox(height: 16),
                    ],
                    TextField(
                      controller: _titre,
                      decoration: InputDecoration(
                        labelText: L.of(context).titre,
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _lieu,
                      decoration: InputDecoration(
                        labelText: L.of(context).lieu,
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _description,
                      maxLines: 4,
                      decoration: InputDecoration(
                        labelText: L.of(context).description,
                      ),
                    ),
                    const SizedBox(height: 8),
                    SwitchListTile(
                      title: Text(L.of(context).journeeEntiere),
                      value: _journeeEntiere,
                      onChanged: (v) => setState(() => _journeeEntiere = v),
                    ),
                    _dateEtHeure(
                      gc,
                      L.of(context).debut,
                      _debut,
                      (d) => setState(() {
                        final duree = _fin.difference(_debut);
                        _debut = d;
                        // La durée suit le début : déplacer un rendez-vous d'une heure ne
                        // doit pas l'allonger silencieusement jusqu'à l'ancienne fin.
                        _fin = d.add(duree);
                      }),
                    ),
                    _dateEtHeure(
                      gc,
                      L.of(context).fin,
                      _fin,
                      (d) => setState(() => _fin = d),
                    ),
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      initialValue: _calendrier,
                      decoration: InputDecoration(
                        labelText: L.of(context).calendrier,
                      ),
                      items: [
                        for (final c in widget.calendriers)
                          DropdownMenuItem(value: c.id, child: Text(c.nom)),
                      ],
                      onChanged: (v) => setState(() => _calendrier = v),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      L.of(context).ceQuiEstChiffre,
                      style: TextStyle(color: gc.estompe, fontSize: 12),
                    ),
                  ],
                ),
        ),
      ),
    );
  }

  Widget _dateEtHeure(
    Gc gc,
    String titre,
    DateTime valeur,
    ValueChanged<DateTime> poser,
  ) => ListTile(
    contentPadding: EdgeInsets.zero,
    title: Text(titre, style: TextStyle(color: gc.estompe, fontSize: 12)),
    subtitle: Text(
      _journeeEntiere
          ? DateFormat.yMMMMd(langueDesDates(context)).format(valeur)
          : DateFormat.yMMMMd(langueDesDates(context)).add_Hm().format(valeur),
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
        poser(
          DateTime(date.year, date.month, date.day, valeur.hour, valeur.minute),
        );
        return;
      }
      final heure = await showTimePicker(
        // ignore: use_build_context_synchronously
        context: context,
        initialTime: TimeOfDay.fromDateTime(valeur),
      );
      if (heure == null) return;
      poser(
        DateTime(date.year, date.month, date.day, heure.hour, heure.minute),
      );
    },
  );
}

enum _Suppression { occurrence, tout }
