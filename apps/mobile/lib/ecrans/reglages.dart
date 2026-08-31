import 'package:flutter/material.dart';

import '../services/agenda.dart';
import '../services/reglages.dart' as service;
import '../services/session.dart';
import '../services/verrouillage.dart' as v;
import '../theme.dart';
import 'equipe.dart';
import 'profil.dart';
import 'sondages.dart';

/// Ce qu'on peut régler, et rien d'autre.
///
/// L'écran ne montre que les fonctions qui existent. Un réglage grisé est pire que son
/// absence : il promet une fonction, et laisse chercher pourquoi elle ne s'active pas.
class EcranDeReglages extends StatefulWidget {
  const EcranDeReglages({
    super.key,
    required this.session,
    required this.verrouillage,
  });

  final Session session;
  final v.Verrouillage verrouillage;

  @override
  State<EcranDeReglages> createState() => _EcranDeReglagesState();
}

class _EcranDeReglagesState extends State<EcranDeReglages> {
  List<Organisation>? _organisations;
  List<service.Horaire>? _horaires;
  String? _erreur;

  @override
  void initState() {
    super.initState();
    _charger();
  }

  Future<void> _charger() async {
    final api = widget.session.api;
    final auth = widget.session.auth;
    if (api == null || auth == null) return;
    try {
      final organisations = await Agenda(api: api, auth: auth).organisations();
      final horaires = await service.Reglages(api: api).horaires();
      if (mounted) {
        setState(() {
          _organisations = organisations;
          _horaires = horaires;
        });
      }
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final session = widget.session;
    // Le coffre s'ouvre par organisation : celles dont la phrase n'a pas déballé la clé
    // sont listées, mais on ne peut pas basculer dessus — leur agenda serait entièrement
    // illisible, et le dire vaut mieux que de l'afficher vide.
    final ouvertes = session.auth?.organisations.toSet() ?? const <String>{};

    return Scaffold(
      appBar: AppBar(title: const Text('Réglages')),
      body: ListView(
        children: [
          if (_erreur != null)
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(_erreur!, style: TextStyle(color: gc.danger)),
            ),
          _titre(gc, 'Compte'),
          ListTile(
            title: const Text('Profil'),
            subtitle: Text(session.email, style: TextStyle(color: gc.estompe)),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push<void>(MaterialPageRoute(
              builder: (_) => EcranDeProfil(session: session),
            )),
          ),
          ListTile(
            title: const Text('Serveur'),
            subtitle: Text(session.serveur, style: TextStyle(color: gc.estompe)),
          ),
          _titre(gc, 'Organisation'),
          if (_organisations == null)
            const Padding(
              padding: EdgeInsets.all(16),
              child: LinearProgressIndicator(),
            )
          else
            RadioGroup<String>(
              groupValue: session.organisation,
              onChanged: (v) => setState(() => session.poserLOrganisation(v)),
              child: Column(
                children: [
                  for (final o in _organisations!)
                    RadioListTile<String>(
                      value: o.id,
                      enabled: ouvertes.contains(o.id),
                      title: Text(o.nom),
                      subtitle: Text(
                        ouvertes.contains(o.id)
                            ? o.role
                            : '${o.role} · coffre fermé pour cette organisation',
                        style: TextStyle(
                          color: ouvertes.contains(o.id) ? gc.estompe : gc.danger,
                          fontSize: 12,
                        ),
                      ),
                    ),
                ],
              ),
            ),
          _titre(gc, 'Disponibilités'),
          if (_horaires == null)
            const Padding(padding: EdgeInsets.all(16), child: LinearProgressIndicator())
          else if (_horaires!.isEmpty)
            ListTile(
              title: Text('Aucun horaire', style: TextStyle(color: gc.estompe)),
              subtitle: Text(
                'Ils se définissent depuis le web.',
                style: TextStyle(color: gc.estompe, fontSize: 12),
              ),
            )
          else
            for (final horaire in _horaires!)
              ListTile(
                title: Text(horaire.nom),
                subtitle: Text(
                  _resume(horaire),
                  style: TextStyle(color: gc.estompe, fontSize: 12),
                ),
              ),
          _titre(gc, 'Organisation'),
          ListTile(
            leading: const Icon(Icons.how_to_vote_outlined),
            title: const Text('Sondages'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push<void>(MaterialPageRoute(
              builder: (_) => EcranDeSondages(session: session),
            )),
          ),
          ListTile(
            leading: const Icon(Icons.people_outline),
            title: const Text('Équipe'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push<void>(MaterialPageRoute(
              builder: (_) => EcranDEquipe(session: session),
            )),
          ),
          _titre(gc, 'Sécurité'),
          // Le délai décide aussi de l'apparition du cadenas dans la barre de l'agenda :
          // à « immédiatement », quitter l'application referme déjà, et le bouton ferait
          // doublon avec ce que le système fait seul.
          RadioGroup<v.DelaiDeVerrouillage>(
            groupValue: widget.verrouillage.choix,
            onChanged: (valeur) async {
              if (valeur == null) return;
              await widget.verrouillage.choisir(valeur);
              if (mounted) setState(() {});
            },
            child: Column(
              children: [
                for (final choix in v.DelaiDeVerrouillage.values)
                  RadioListTile<v.DelaiDeVerrouillage>(
                    value: choix,
                    title: Text(choix.libelle),
                  ),
              ],
            ),
          ),
          ListTile(
            leading: const Icon(Icons.lock_outline),
            title: const Text('Verrouiller le coffre'),
            subtitle: Text(
              'Les clés quittent la mémoire ; la session reste ouverte.',
              style: TextStyle(color: gc.estompe, fontSize: 12),
            ),
            onTap: session.verrouiller,
          ),
          ListTile(
            leading: Icon(Icons.logout, color: gc.danger),
            title: Text('Se déconnecter', style: TextStyle(color: gc.danger)),
            onTap: session.seDeconnecter,
          ),
        ],
      ),
    );
  }

  /// Le résumé d'un horaire : les jours qu'il couvre.
  ///
  /// Le nom du jour vient de `RegleDHoraire.jour`, qui **refuse** une valeur hors bornes
  /// plutôt que de la ramener par modulo — un `weekday` de 42 affiché « lundi » serait une
  /// valeur fausse présentée avec l'assurance d'une vraie.
  String _resume(service.Horaire horaire) {
    if (horaire.regles.isEmpty) return 'Aucune plage · ${horaire.fuseau}';
    final jours = <String>{for (final regle in horaire.regles) regle.jour};
    return '${jours.join(', ')} · ${horaire.fuseau}';
  }

  Widget _titre(Gc gc, String texte) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 20, 16, 6),
        child: Text(
          texte.toUpperCase(),
          style: TextStyle(color: gc.estompe, fontSize: 11, letterSpacing: 1),
        ),
      );
}
