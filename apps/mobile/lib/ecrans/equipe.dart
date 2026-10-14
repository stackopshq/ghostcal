import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../modeles/adresse.dart';

import '../services/erreurs.dart';
import '../services/reglages.dart';
import '../services/session.dart';
import '../theme.dart';
import '../l10n/generated/app_localisations.dart';

/// Les membres de l'organisation, et ce qu'on peut leur faire.
class EcranDEquipe extends StatefulWidget {
  const EcranDEquipe({super.key, required this.session});

  final Session session;

  @override
  State<EcranDEquipe> createState() => _EcranDEquipeState();
}

class _EcranDEquipeState extends State<EcranDEquipe> {
  List<Membre>? _membres;
  String? _erreur;

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
    setState(() => _erreur = null);
    try {
      final membres = await service.membres();
      if (mounted) setState(() => _membres = membres);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, L.of(context)));
    }
  }

  Future<void> _changerLeRole(Membre membre, String role) async {
    final service = _service;
    if (service == null) return;
    try {
      // Le serveur rend la liste à jour : on la réutilise plutôt que de relire, sinon
      // deux appels donneraient deux vérités possibles entre-temps.
      final membres = await service.changerLeRole(membre.id, role: role);
      if (mounted) setState(() => _membres = membres);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, L.of(context)));
    }
  }

  Future<void> _retirer(Membre membre) async {
    final service = _service;
    if (service == null) return;
    final confirme = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(
          'Retirer ${membre.nom.isEmpty ? membre.courriel : membre.nom} ?',
        ),
        content: Text(L.of(context).perteDAccesOrganisation),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(c, false),
            child: Text(L.of(context).annuler),
          ),
          TextButton(
            onPressed: () => Navigator.pop(c, true),
            child: Text(L.of(context).retirer),
          ),
        ],
      ),
    );
    if (confirme != true) return;
    try {
      await service.retirerLeMembre(membre.id);
      await _charger();
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, L.of(context)));
    }
  }

  Future<void> _inviter() async {
    final service = _service;
    final site = AdresseDeServeur.normaliser(widget.session.serveur);
    if (service == null || site == null) return;
    final organisation = widget.session.organisation;
    final invitation = await showModalBottomSheet<InvitationCreee>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _FeuilleDInvitation(
        envoyer: (email, role) => service.inviter(
          email: email,
          role: role,
          site: site,
          clePriveeDeLOrganisation: organisation == null
              ? null
              : widget.session.auth?.clesDe(organisation)?.privee,
        ),
      ),
    );
    if (invitation == null || !mounted) return;
    await _charger();
    if (!mounted) return;
    final lien = invitation.lien;
    await showDialog<void>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(L.of(context).invitationEnvoyee(invitation.email)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(lien == null ? L.of(context).invitationSansCle : L.of(context).invitationLienSecurise),
            if (lien != null) ...[
              const SizedBox(height: 12),
              SelectableText(lien.toString(), style: const TextStyle(fontSize: 12)),
            ],
          ],
        ),
        actions: [
          if (lien != null)
            TextButton(
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: lien.toString()));
                if (c.mounted) Navigator.pop(c);
              },
              child: Text(L.of(context).copierLeLien),
            ),
          TextButton(onPressed: () => Navigator.pop(c), child: Text(L.of(context).fermer)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final membres = _membres;
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
        appBar: AppBar(title: Text(L.of(context).equipe)),
        floatingActionButton: FloatingActionButton.extended(
          heroTag: 'equipe',
          icon: const Icon(Icons.person_add_alt),
          label: Text(L.of(context).inviter),
          onPressed: _inviter,
        ),
        body: ContenuBorne(
          child: RefreshIndicator(
            onRefresh: _charger,
            child: _erreur != null
                ? ListView(
                    padding: const EdgeInsets.all(20),
                    children: [
                      Text(_erreur!, style: TextStyle(color: gc.danger)),
                    ],
                  )
                : membres == null
                ? const Center(child: CircularProgressIndicator())
                : ListView.separated(
                    itemCount: membres.length,
                    separatorBuilder: (_, _) =>
                        Divider(height: 1, color: gc.bordure),
                    itemBuilder: (_, i) => _ligne(gc, membres[i]),
                  ),
          ),
        ),
      ),
    );
  }

  Widget _ligne(Gc gc, Membre membre) {
    // Le propriétaire ne se modifie pas depuis ici : lui retirer son rôle ou le sortir de
    // l'organisation pourrait laisser celle-ci sans personne pour l'administrer.
    final modifiable = membre.role != 'owner';
    return ListTile(
      title: Text(membre.nom.isEmpty ? membre.courriel : membre.nom),
      subtitle: Text(
        membre.nom.isEmpty
            ? membre.roleLisible(L.of(context))
            : '${membre.courriel} · ${membre.roleLisible(L.of(context))}',
        style: TextStyle(fontSize: 12, color: gc.estompe),
      ),
      trailing: !modifiable
          ? Icon(Icons.shield_outlined, size: 18, color: gc.estompe)
          : PopupMenuButton<String>(
              itemBuilder: (_) => [
                PopupMenuItem(
                  value: 'admin',
                  child: Text(L.of(context).roleAdministrateur),
                ),
                PopupMenuItem(value: 'member', child: Text(L.of(context).roleMembre)),
                PopupMenuItem(
                  value: '-',
                  child: Text(L.of(context).retirerDeLEquipe),
                ),
              ],
              onSelected: (choix) => choix == '-'
                  ? _retirer(membre)
                  : _changerLeRole(membre, choix),
            ),
    );
  }
}

class _FeuilleDInvitation extends StatefulWidget {
  const _FeuilleDInvitation({required this.envoyer});

  final Future<InvitationCreee> Function(String email, String role) envoyer;

  @override
  State<_FeuilleDInvitation> createState() => _FeuilleDInvitationState();
}

class _FeuilleDInvitationState extends State<_FeuilleDInvitation> {
  final _email = TextEditingController();
  String _role = 'member';
  bool _occupe = false;
  String? _erreur;

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _envoyer() async {
    setState(() {
      _occupe = true;
      _erreur = null;
    });
    try {
      final invitation = await widget.envoyer(_email.text.trim(), _role);
      if (mounted) Navigator.of(context).pop(invitation);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, L.of(context)));
    } finally {
      if (mounted) setState(() => _occupe = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final l = L.of(context);
    final valide = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(_email.text.trim());
    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 20,
        bottom: MediaQuery.of(context).viewInsets.bottom + 20,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(l.inviterUnMembre,
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: gc.encre)),
          const SizedBox(height: 16),
          TextField(
            controller: _email,
            autofocus: true,
            keyboardType: TextInputType.emailAddress,
            onChanged: (_) => setState(() {}),
            decoration: InputDecoration(labelText: l.adresseEmail),
          ),
          const SizedBox(height: 12),
          SegmentedButton<String>(
            showSelectedIcon: false,
            segments: [
              ButtonSegment(value: 'member', label: Text(l.roleMembre)),
              ButtonSegment(value: 'admin', label: Text(l.roleAdministrateur)),
            ],
            selected: {_role},
            onSelectionChanged: (v) => setState(() => _role = v.first),
          ),
          if (_erreur != null) ...[
            const SizedBox(height: 12),
            Text(_erreur!, style: TextStyle(color: gc.danger, fontSize: 13)),
          ],
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: !valide || _occupe ? null : _envoyer,
              child: _occupe
                  ? const SizedBox(
                      width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : Text(l.inviter),
            ),
          ),
        ],
      ),
    );
  }
}
