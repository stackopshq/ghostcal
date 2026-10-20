import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../services/agenda.dart' show Agenda;
import '../services/erreurs.dart';
import '../services/reglages.dart';
import '../services/session.dart';
import '../services/vignette.dart';
import '../theme.dart';
import 'choix_du_fuseau.dart';
import '../l10n/generated/app_localisations.dart';

/// Le profil : le nom, le fuseau, et la photo.
///
/// **L'adresse e-mail ne s'y modifie pas**, et le champ n'est pas grisé mais absent : la
/// changer demande une vérification que cette route ne déclenche pas. Un champ désactivé
/// promettrait une fonction inexistante et laisserait chercher comment l'activer.
class EcranDeProfil extends StatefulWidget {
  const EcranDeProfil({super.key, required this.session, this.vignette = const Vignette()});

  final Session session;

  /// Le ré-encodage de la photo choisie. Sans effet hors macOS — voir [Vignette].
  /// Injectable pour qu'un témoin puisse éprouver le chemin sans canal de plateforme.
  final Vignette vignette;

  @override
  State<EcranDeProfil> createState() => _EcranDeProfilState();
}

class _EcranDeProfilState extends State<EcranDeProfil> {
  final _nom = TextEditingController();
  final _fuseau = TextEditingController();
  Profil? _profil;
  Uint8List? _photo;
  bool _photoEnCours = false;
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
      await _chargerLaPhoto(service, profil);
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, L.of(context)));
    }
  }

  Future<void> _chargerLaPhoto(Reglages service, Profil profil) async {
    Uint8List? octets;
    if (profil.aUnePhoto) {
      try {
        octets = await service.photo(profil.id);
      } on Object {
        octets = null; // initials stay; the photo is a nicety, not worth an error
      }
    }
    if (mounted) setState(() => _photo = octets);
  }

  /// Server limit before re-encoding (see `application/avatars.py`).
  static const _octetsMax = 2 * 1024 * 1024;

  Future<void> _choisirUnePhoto() async {
    final service = _service;
    if (service == null) return;
    final l = L.of(context);
    // Downscaled on the device: a 12 MP camera shot would exceed the server's 2 MB, and it
    // is re-encoded to 512 px there anyway.
    final image = await ImagePicker().pickImage(
      source: ImageSource.gallery,
      maxWidth: 1024,
      maxHeight: 1024,
      imageQuality: 88,
    );
    if (image == null || !mounted) return;
    setState(() {
      _photoEnCours = true;
      _erreur = null;
      _message = null;
    });
    try {
      // ─── Sur macOS, les trois options ci-dessus n'ont rien fait ───
      //
      // `image_picker_macos` les ignore **en silence** : ce n'est qu'un `NSOpenPanel`, et
      // le fichier remonte tel que l'utilisateur l'a choisi. Une photo d'iPhone arrive
      // donc en HEIC, que le serveur refuse (`FORMATS_ACCEPTES`), et en plusieurs
      // méga-octets, que la borne ci-dessous refuse avant lui. Les deux échecs tombent sur
      // le parcours normal, et aucun ne nomme sa cause.
      //
      // [Vignette] fait le travail avec le décodeur du système — le seul qui lise le HEIC.
      // Ailleurs elle rend `null` et `image_picker` a déjà fait le sien.
      final reduite = await widget.vignette.reduire(image.path);
      final octets = reduite ?? await image.readAsBytes();
      if (octets.length > _octetsMax) {
        setState(() => _erreur = l.photoTropLourde);
        return;
      }
      // Le nom porte l'extension du **résultat** et non celle de la source : le serveur ne
      // croit ni l'extension ni le type annoncé, mais lui présenter « photo.heic » pour du
      // JPEG serait écrire quelque chose de faux parce que personne ne le lit.
      final nom = reduite == null ? image.name : _enJpeg(image.name);
      await service.televerserLaPhoto(octets, nom);
      final profil = await service.profil();
      if (!mounted) return;
      setState(() {
        _profil = profil;
        _photo = octets;
        _message = l.photoEnregistree;
      });
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, l));
    } finally {
      if (mounted) setState(() => _photoEnCours = false);
    }
  }

  /// Le nom du fichier, extension remplacée par celle de ce qu'on envoie vraiment.
  static String _enJpeg(String nom) {
    final point = nom.lastIndexOf('.');
    return '${point <= 0 ? nom : nom.substring(0, point)}.jpg';
  }

  Future<void> _retirerLaPhotoTeleversee() async {
    final service = _service;
    if (service == null) return;
    final l = L.of(context);
    setState(() {
      _photoEnCours = true;
      _erreur = null;
      _message = null;
    });
    try {
      await service.retirerLaPhotoTeleversee();
      final profil = await service.profil();
      if (!mounted) return;
      setState(() {
        _profil = profil;
        _photo = null;
        _message = l.photoRetiree;
      });
    } on Object catch (e) {
      if (mounted) setState(() => _erreur = lisible(e, l));
    } finally {
      if (mounted) setState(() => _photoEnCours = false);
    }
  }

  Widget _blocPhoto(Gc gc, Profil profil) {
    final l = L.of(context);
    final mots = profil.nom.trim().split(RegExp(r'\s+')).where((m) => m.isNotEmpty);
    final initiales = mots.isEmpty ? '?' : mots.take(2).map((m) => m[0].toUpperCase()).join();
    return Row(
      children: [
        CircleAvatar(
          key: const Key('profil.photo'),
          radius: 34,
          backgroundColor: gc.surface2,
          foregroundImage: _photo == null ? null : MemoryImage(_photo!),
          child: Text(initiales, style: TextStyle(color: gc.estompe, fontSize: 20)),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              OutlinedButton.icon(
                key: const Key('profil.choisirPhoto'),
                onPressed: _photoEnCours ? null : _choisirUnePhoto,
                icon: _photoEnCours
                    ? const SizedBox(
                        height: 16,
                        width: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.photo_library_outlined),
                label: Text(l.choisirUnePhoto),
              ),
              if (profil.aUnePhoto)
                TextButton(
                  key: const Key('profil.retirerPhoto'),
                  onPressed: _photoEnCours ? null : _retirerLaPhotoTeleversee,
                  child: Text(l.retirerLaPhotoTeleversee),
                ),
            ],
          ),
        ),
      ],
    );
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
      if (mounted) setState(() => _erreur = lisible(e, L.of(context)));
    } finally {
      if (mounted) setState(() => _occupe = false);
    }
  }

  Future<void> _choisirLeFuseau() async {
    final choisi = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const ChoixDuFuseau(),
    );
    if (choisi != null && mounted) setState(() => _fuseau.text = choisi);
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
                    _libelle(gc, L.of(context).photoDeProfil),
                    const SizedBox(height: 10),
                    _blocPhoto(gc, profil),
                    const SizedBox(height: 18),
                    _libelle(gc, L.of(context).adresseEmail),
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
                    _libelle(gc, L.of(context).nom),
                    const SizedBox(height: 7),
                    TextField(controller: _nom),
                    const SizedBox(height: 18),
                    _libelle(gc, L.of(context).fuseauHoraire),
                    const SizedBox(height: 7),
                    // A picker rather than free text: "Europe/Zurich" typed by hand was
                    // one typo away from a 422.
                    TextField(
                      key: const Key('profil.fuseau'),
                      controller: _fuseau,
                      readOnly: true,
                      decoration: const InputDecoration(suffixIcon: Icon(Icons.expand_more)),
                      onTap: _choisirLeFuseau,
                    ),
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
                          : Text(L.of(context).enregistrer),
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
