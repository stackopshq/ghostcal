import 'package:flutter/material.dart';

import '../services/agenda.dart';
import '../services/biometrie.dart';
import '../services/reglages.dart' as service;
import '../services/session.dart';
import '../services/verrouillage.dart' as v;
import '../theme.dart';
import 'equipe.dart';
import 'profil.dart';
import 'sondages.dart';
import '../l10n/generated/app_localisations.dart';

/// Ce qu'on peut régler, et rien d'autre.
///
/// L'écran ne montre que les fonctions qui existent. Un réglage grisé est pire que son
/// absence : il promet une fonction, et laisse chercher pourquoi elle ne s'active pas.
class EcranDeReglages extends StatefulWidget {
  const EcranDeReglages({
    super.key,
    required this.session,
    required this.verrouillage,
    this.biometrie,
  });

  final Session session;
  final v.Verrouillage verrouillage;

  /// Le magasin scellé, injectable pour les témoins — même couture que
  /// [EcranDeConnexion]. Sans elle, le retrait du sceau ne serait vérifiable que sur un
  /// appareil, donc par personne.
  final Biometrie? biometrie;

  @override
  State<EcranDeReglages> createState() => _EcranDeReglagesState();
}

class _EcranDeReglagesState extends State<EcranDeReglages> {
  List<Organisation>? _organisations;
  List<service.Horaire>? _horaires;
  String? _erreur;

  late final _biometrie = widget.biometrie ?? Biometrie();

  /// La biométrie utilisable sur cet appareil, `null` s'il n'y en a pas.
  Empreinte? _empreinte;

  /// L'état du sceau, **tel que le magasin l'a rendu** — pas un booléen de réglage.
  ///
  /// C'est la leçon du 2026-09-25 appliquée aux réglages : GhostPass affichait « actif »
  /// en lisant une préférence, alors que le trousseau, lui, n'avait plus rien. Un réglage
  /// qui se souvient de ce qu'on lui a dit ment dès que la plateforme change d'avis
  /// derrière lui. Celui-ci ne se souvient de rien et **redemande** à chaque affichage.
  ///
  /// `null` tant que la réponse n'est pas revenue : ce n'est pas « absent ».
  Issue? _sceau;

  /// Ce qu'on vient de faire au sceau, quand ça mérite d'être dit.
  String? _motDuSceau;

  @override
  void initState() {
    super.initState();
    _charger();
    _relireLeSceau();
  }

  /// Relit l'état du sceau **sans** déclencher la biométrie : `sceau()` interroge la
  /// présence, pas la valeur. Ouvrir les réglages ne doit pas demander un visage.
  Future<void> _relireLeSceau() async {
    final empreinte = await _biometrie.disponible();
    final etat = empreinte == null ? null : await _biometrie.sceau();
    if (!mounted) return;
    setState(() {
      _empreinte = empreinte;
      _sceau = etat;
    });
  }

  Future<void> _retirerLeSceau() async {
    await _biometrie.oublier();
    if (!mounted) return;
    setState(() => _motDuSceau = L.of(context).sceauRetire);
    // On relit plutôt que de poser « absent » de confiance : `oublier` avale ses erreurs,
    // et affirmer un retrait qu'on n'a pas vérifié serait le réglage menteur, inversé.
    await _relireLeSceau();
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
      appBar: AppBar(title: Text(L.of(context).ongletReglages)),
      body: ListView(
        // La dernière ligne finissait au ras de la barre d'onglets : rien n'indiquait
        // qu'il restait à faire défiler, et une section coupée après son premier élément
        // se lit comme complète. Constaté à l'écran — voir le témoin de visibilité.
        padding: const EdgeInsets.only(bottom: 24),
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
          _titre(gc, L.of(context).securite),
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
                    title: Text(choix.libelle(L.of(context))),
                  ),
              ],
            ),
          ),
          ListTile(
            leading: const Icon(Icons.lock_outline),
            title: Text(L.of(context).verrouillerLeCoffre),
            subtitle: Text(
              L.of(context).clesQuittentLaMemoire,
              style: TextStyle(color: gc.estompe, fontSize: 12),
            ),
            onTap: session.verrouiller,
          ),
          _ligneDuSceau(gc),
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
                            : L.of(context).coffreFermePourOrganisation(o.role),
                        style: TextStyle(
                          color: ouvertes.contains(o.id) ? gc.estompe : gc.danger,
                          fontSize: 12,
                        ),
                      ),
                    ),
                ],
              ),
            ),
          _titre(gc, L.of(context).disponibilites),
          if (_horaires == null)
            const Padding(padding: EdgeInsets.all(16), child: LinearProgressIndicator())
          else if (_horaires!.isEmpty)
            ListTile(
              title: Text(L.of(context).aucunHoraire, style: TextStyle(color: gc.estompe)),
              subtitle: Text(
                L.of(context).horairesDepuisLeWeb,
                style: TextStyle(color: gc.estompe, fontSize: 12),
              ),
            )
          else
            for (final horaire in _horaires!)
              ListTile(
                title: Text(horaire.nom),
                subtitle: Text(
                  _resume(context, horaire),
                  style: TextStyle(color: gc.estompe, fontSize: 12),
                ),
              ),
          _titre(gc, 'Collaboration'),
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
            title: Text(L.of(context).equipe),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push<void>(MaterialPageRoute(
              builder: (_) => EcranDEquipe(session: session),
            )),
          ),
          ListTile(
            leading: Icon(Icons.logout, color: gc.danger),
            title: Text(L.of(context).seDeconnecter, style: TextStyle(color: gc.danger)),
            onTap: session.seDeconnecter,
          ),
        ],
      ),
    );
  }

  /// L'état du sceau biométrique, et de quoi le retirer.
  ///
  /// ─── Pourquoi ce n'est pas un interrupteur ───
  ///
  /// Un interrupteur a deux positions, et c'est précisément l'erreur qu'on répare. Le
  /// trousseau rend **trois** réponses, et aucune ne se peint en « activé » ou
  /// « désactivé » sans mentir sur l'une des autres :
  ///
  /// - scellé, la clé est vivante ;
  /// - rien de scellé, ou le sceau est mort avec l'enrôlement qui l'a créé ;
  /// - **le magasin n'a pas répondu** — ni oui ni non, et c'est celui-là qui a coûté une
  ///   panne à GhostPass le 2026-09-25, affiché « actif » alors qu'il n'y avait plus rien.
  ///
  /// Poser le sceau ne se fait pas d'ici : cela demande la phrase, et la phrase n'est plus
  /// en mémoire une fois le coffre ouvert. La proposition revient là où le secret est sous
  /// la main, c'est-à-dire au prochain déverrouillage. **Le retrait**, lui, n'a besoin de
  /// rien et se fait ici.
  Widget _ligneDuSceau(Gc gc) {
    final l = L.of(context);
    final empreinte = _empreinte;

    final (String etat, bool retirable) = switch ((empreinte, _sceau)) {
      // Pas de matériel : le dire, plutôt qu'une ligne qui ne fera jamais rien.
      (null, _) => (l.sansBiometrieSurCetAppareil, false),
      // La réponse n'est pas encore revenue. Elle n'est pas « non ».
      (_, null) => ('', false),
      (final e?, Issue.ouverte) => (l.sceauPose(e.nom(l)), true),
      (_, Issue.absente) => (l.sceauAbsent, false),
      (_, Issue.invalidee) => (l.sceauInvalide, true),
      // `pasMaintenant` et `refusee` ne peuvent pas sortir de `sceau()`, qui ne présente
      // rien. S'ils arrivaient quand même, ils diraient la même chose : on ne sait pas.
      // Le `switch` est exhaustif — une issue ajoutée sans être nommée ici ne compile pas.
      (_, Issue.pasMaintenant) ||
      (_, Issue.refusee) ||
      (_, Issue.echec) =>
        (l.sceauIndetermine, true),
    };

    return ListTile(
      key: const Key('ligne.sceau'),
      leading: Icon(empreinte?.icone ?? Icons.face_retouching_off_outlined),
      title: Text(l.sceauBiometrique),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (etat.isNotEmpty)
            Text(etat, style: TextStyle(color: gc.estompe, fontSize: 12)),
          if (_motDuSceau != null)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                _motDuSceau!,
                key: const Key('mot.sceau'),
                style: TextStyle(color: gc.estompe, fontSize: 12),
              ),
            ),
        ],
      ),
      trailing: retirable
          ? TextButton(
              key: const Key('bouton.retirer.sceau'),
              onPressed: _retirerLeSceau,
              style: TextButton.styleFrom(foregroundColor: gc.danger),
              child: Text(l.retirerLeSceau),
            )
          : null,
    );
  }

  /// Le résumé d'un horaire : les jours qu'il couvre.
  ///
  /// Le nom du jour vient de `RegleDHoraire.jour`, qui **refuse** une valeur hors bornes
  /// plutôt que de la ramener par modulo — un `weekday` de 42 affiché « lundi » serait une
  /// valeur fausse présentée avec l'assurance d'une vraie.
  String _resume(BuildContext context, service.Horaire horaire) {
    if (horaire.regles.isEmpty) return L.of(context).aucunePlage(horaire.fuseau);
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
