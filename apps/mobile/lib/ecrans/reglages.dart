import 'package:flutter/material.dart';

import '../services/agenda.dart';
import '../services/session.dart';
import '../theme.dart';

/// Ce qu'on peut régler, et rien d'autre.
///
/// L'écran ne montre que les fonctions qui existent. Un réglage grisé est pire que son
/// absence : il promet une fonction, et laisse chercher pourquoi elle ne s'active pas.
class EcranDeReglages extends StatefulWidget {
  const EcranDeReglages({super.key, required this.session});

  final Session session;

  @override
  State<EcranDeReglages> createState() => _EcranDeReglagesState();
}

class _EcranDeReglagesState extends State<EcranDeReglages> {
  List<Organisation>? _organisations;
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
      if (mounted) setState(() => _organisations = organisations);
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
            title: const Text('Adresse e-mail'),
            subtitle: Text(session.email, style: TextStyle(color: gc.estompe)),
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
          _titre(gc, 'Sécurité'),
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

  Widget _titre(Gc gc, String texte) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 20, 16, 6),
        child: Text(
          texte.toUpperCase(),
          style: TextStyle(color: gc.estompe, fontSize: 11, letterSpacing: 1),
        ),
      );
}
