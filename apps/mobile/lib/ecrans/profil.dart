import 'package:flutter/material.dart';

import '../services/agenda.dart' show Agenda;
import '../services/reglages.dart';
import '../services/session.dart';
import '../theme.dart';
import '../l10n/generated/app_localisations.dart';

/// Le profil : le nom, le fuseau, et la photo.
///
/// **L'adresse e-mail ne s'y modifie pas**, et le champ n'est pas grisé mais absent : la
/// changer demande une vérification que cette route ne déclenche pas. Un champ désactivé
/// promettrait une fonction inexistante et laisserait chercher comment l'activer.
class EcranDeProfil extends StatefulWidget {
  const EcranDeProfil({super.key, required this.session});

  final Session session;

  @override
  State<EcranDeProfil> createState() => _EcranDeProfilState();
}

class _EcranDeProfilState extends State<EcranDeProfil> {
  final _nom = TextEditingController();
  final _fuseau = TextEditingController();
  Profil? _profil;
  bool _retirerLaPhoto = false;
  bool _occupe = false;
  String? _erreur;
  String? _message;

  @override
  void initState() {
    super.initState();
    _charger();
  }

  @override
  void dispose() {
    _nom.dispose();
    _fuseau.dispose();
    super.dispose();
  }

  Reglages? get _service {
    final api = widget.session.api;
    return api == null ? null : Reglages(api: api);
  }

  Future<void> _charger() async {
    final service = _service;
    if (service == null) return;
    try {
      final profil = await service.profil();
      if (!mounted) return;
      setState(() {
        _profil = profil;
        _nom.text = profil.nom;
        _fuseau.text = profil.fuseau;
        _retirerLaPhoto = false;
      });
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    }
  }

  Future<void> _enregistrer() async {
    final service = _service;
    final profil = _profil;
    if (service == null || profil == null) return;
    setState(() {
      _occupe = true;
      _erreur = null;
      _message = null;
    });
    try {
      // `avatar` nul part **explicitement** : la route remplace, donc omettre le champ
      // dirait « ne touche pas » là où l'utilisateur demande « efface ».
      final mis = await service.enregistrerLeProfil(
        nom: _nom.text.trim(),
        fuseau: _fuseau.text.trim(),
        avatar: _retirerLaPhoto ? null : profil.avatar,
      );
      if (!mounted) return;
      setState(() {
        _profil = mis;
        _retirerLaPhoto = false;
        _message = L.of(context).profilEnregistre;
      });
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = '$e');
    } finally {
      if (mounted) setState(() => _occupe = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final profil = _profil;
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
        appBar: AppBar(title: Text(L.of(context).profil)),
        body: ContenuBorne(
          child: profil == null
              ? Center(
                  child: _erreur == null
                      ? const CircularProgressIndicator()
                      : Padding(
                          padding: const EdgeInsets.all(20),
                          child: Text(
                            _erreur!,
                            style: TextStyle(color: gc.danger),
                          ),
                        ),
                )
              : ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    _libelle(gc, 'Adresse e-mail'),
                    const SizedBox(height: 7),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 14,
                      ),
                      decoration: BoxDecoration(
                        color: gc.surface2,
                        borderRadius: BorderRadius.circular(Mesures.rayon),
                        border: Border.all(color: gc.bordure),
                      ),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(
                              profil.courriel,
                              style: TextStyle(color: gc.estompe),
                            ),
                          ),
                          // Une adresse non vérifiée se dit : le serveur n'enverra pas les
                          // rappels dessus, et rien d'autre à l'écran ne l'expliquerait.
                          if (!profil.courrielVerifie)
                            Text(
                              L.of(context).nonVerifiee,
                              style: TextStyle(color: gc.danger, fontSize: 12),
                            ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      L.of(context).changementDAdresseParLeWeb,
                      style: TextStyle(color: gc.estompe, fontSize: 12),
                    ),
                    const SizedBox(height: 18),
                    _libelle(gc, 'Nom'),
                    const SizedBox(height: 7),
                    TextField(controller: _nom),
                    const SizedBox(height: 18),
                    _libelle(gc, 'Fuseau horaire'),
                    const SizedBox(height: 7),
                    TextField(controller: _fuseau),
                    const SizedBox(height: 8),
                    TextButton(
                      onPressed: () async {
                        final ici = await Agenda.fuseauCourant();
                        if (mounted) setState(() => _fuseau.text = ici);
                      },
                      child: Text(L.of(context).utiliserLeFuseauDeLAppareil),
                    ),
                    if (profil.avatar != null) ...[
                      const SizedBox(height: 8),
                      SwitchListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(L.of(context).retirerLaPhoto),
                        subtitle: Text(
                          L.of(context).photoEffaceeALEnregistrement,
                          style: TextStyle(color: gc.estompe, fontSize: 12),
                        ),
                        value: _retirerLaPhoto,
                        onChanged: (v) => setState(() => _retirerLaPhoto = v),
                      ),
                    ],
                    if (_erreur != null) ...[
                      const SizedBox(height: 12),
                      Text(
                        _erreur!,
                        style: TextStyle(color: gc.danger, fontSize: 13),
                      ),
                    ],
                    if (_message != null) ...[
                      const SizedBox(height: 12),
                      Text(
                        _message!,
                        style: TextStyle(color: gc.succes, fontSize: 13),
                      ),
                    ],
                    const SizedBox(height: 20),
                    BoutonPrincipal(
                      onPressed: _occupe ? null : _enregistrer,
                      child: _occupe
                          ? const SizedBox(
                              height: 18,
                              width: 18,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Gc.surAccent,
                              ),
                            )
                          : const Text('Enregistrer'),
                    ),
                  ],
                ),
        ),
      ),
    );
  }

  Widget _libelle(Gc gc, String texte) => Text(
    texte.toUpperCase(),
    style: TextStyle(
      color: gc.estompe,
      fontSize: 11,
      fontWeight: FontWeight.w600,
      letterSpacing: 1.1,
    ),
  );
}
