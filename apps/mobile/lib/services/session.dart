import 'package:flutter/foundation.dart';

import '../modeles/adresse.dart';
import 'api.dart';
import 'auth.dart';
import 'trousseau.dart';

/// L'état de la session, tel que les écrans le voient.
///
/// Trois états, et non deux — c'est la distinction que porte [Auth] et qu'il serait
/// tentant d'aplatir :
///
/// - **dehors** : aucun jeton ;
/// - **coffre fermé** : le serveur nous reconnaît, mais la phrase n'a pas ouvert les
///   clés. L'agenda existe et reste illisible ;
/// - **ouvert** : tout est lisible.
///
/// Aplatir les deux derniers renverrait à l'écran de connexion quelqu'un qui est
/// parfaitement authentifié, sans lui dire que c'est sa phrase qui ne va pas.
enum Etat { dehors, coffreFerme, ouvert }

class Session extends ChangeNotifier {
  Etat _etat = Etat.dehors;
  bool _occupe = false;
  String? _erreur;
  String? _raisonDuCoffre;

  /// L'adresse et l'e-mail saisis, conservés entre deux lancements : les retaper à chaque
  /// fois serait la première friction d'une application qu'on ouvre dix fois par jour.
  String serveur = '';
  String email = '';

  ClientAPI? api;
  Auth? auth;
  String? _organisation;
  bool _sessionEnregistree = false;

  Etat get etat => _etat;
  bool get occupe => _occupe;
  String? get erreur => _erreur;
  String? get raisonDuCoffre => _raisonDuCoffre;
  String? get organisation => _organisation;

  /// Une session enregistrée attend-elle sa phrase ?
  ///
  /// On ne peut pas reprendre une session complètement : les jetons rouvrent le compte,
  /// jamais le coffre. L'écran demande donc la phrase seule, sans redemander l'adresse ni
  /// l'e-mail — c'est le cas courant au lancement.
  bool get sessionEnregistree => _sessionEnregistree && serveur.isNotEmpty;

  /// Relit ce que le trousseau a gardé. À appeler avant d'afficher quoi que ce soit,
  /// sinon l'écran de connexion s'affiche vide une fraction de seconde chez quelqu'un
  /// dont la session est parfaitement valide.
  Future<void> amorcer() async {
    serveur = await Trousseau.lire(Trousseau.serveur) ?? '';
    email = await Trousseau.lire(Trousseau.email) ?? '';
    _sessionEnregistree =
        await Trousseau.lire(Trousseau.jetonDeRafraichissement) != null;
    notifyListeners();
  }

  /// Poser un état à la main, pour les témoins de comportement.
  ///
  /// Les trois visages de l'écran de connexion dépendent d'états que seul le réseau
  /// produit ; sans ces deux entrées, la règle « connecté mais coffre fermé » ne serait
  /// vérifiable que contre un vrai serveur, donc jamais.
  @visibleForTesting
  void debugPoserEtat(Etat etat, {String? raison}) {
    _etat = etat;
    _raisonDuCoffre = raison;
    notifyListeners();
  }

  @visibleForTesting
  void debugPoserSessionEnregistree(bool valeur) {
    _sessionEnregistree = valeur;
    notifyListeners();
  }

  void poserLOrganisation(String? id) {
    _organisation = id;
    api?.poserLOrganisation(id);
    notifyListeners();
  }

  Future<void> seConnecter({required String motDePasse}) async {
    final base = AdresseDeServeur.normaliser(serveur);
    if (base == null) {
      _erreur = 'Adresse de serveur invalide.';
      notifyListeners();
      return;
    }
    await _pendant(() async {
      final client = ClientAPI(base: base);
      final service = Auth(client);
      final echecDuCoffre =
          await service.seConnecter(email: email, motDePasse: motDePasse);
      _adopter(client, service, base);
      _etat = echecDuCoffre == null ? Etat.ouvert : Etat.coffreFerme;
      _raisonDuCoffre = echecDuCoffre;
      await _enregistrer(client, base);
    });
  }

  /// Reprend la session enregistrée, puis ouvre le coffre avec la phrase donnée.
  Future<void> reprendre({required String phrase, bool parRecuperation = false}) async {
    final base = AdresseDeServeur.normaliser(serveur);
    final acces = await Trousseau.lire(Trousseau.jetonDAcces);
    final rafraichissement = await Trousseau.lire(Trousseau.jetonDeRafraichissement);
    if (base == null || acces == null || rafraichissement == null) {
      _etat = Etat.dehors;
      notifyListeners();
      return;
    }

    _occupe = true;
    _erreur = null;
    notifyListeners();
    final client = ClientAPI(base: base)
      ..poserLesJetons(Jetons(acces: acces, rafraichissement: rafraichissement));
    final service = Auth(client);
    try {
      await service.deverrouiller(phrase: phrase, parRecuperation: parRecuperation);
      _adopter(client, service, base);
      _etat = Etat.ouvert;
      _raisonDuCoffre = null;
      // Les jetons ont pu tourner pendant l'appel : on réenregistre ceux qui valent.
      await _enregistrer(client, base);
    } on Object catch (e) {
      // Un jeton périmé et une phrase fausse ne se corrigent pas de la même façon :
      // l'un demande de se reconnecter, l'autre de retaper. Les confondre enverrait
      // quelqu'un ressaisir une phrase juste.
      if (client.jetons == null) {
        await seDeconnecter();
        _erreur = 'La session a expiré. Reconnectez-vous.';
      } else {
        _erreur = '$e';
      }
    } finally {
      _occupe = false;
      notifyListeners();
    }
  }

  /// Ouvre le coffre d'une session déjà authentifiée — le cas « connecté, coffre fermé ».
  Future<void> deverrouiller({required String phrase, bool parRecuperation = false}) async {
    final service = auth;
    if (service == null) return;
    await _pendant(() async {
      await service.deverrouiller(phrase: phrase, parRecuperation: parRecuperation);
      _etat = Etat.ouvert;
      _raisonDuCoffre = null;
    });
  }

  void verrouiller() {
    auth?.verrouiller();
    _etat = Etat.coffreFerme;
    _raisonDuCoffre = null;
    notifyListeners();
  }

  Future<void> seDeconnecter() async {
    auth?.verrouiller();
    api?.poserLesJetons(null);
    api = null;
    auth = null;
    _organisation = null;
    _sessionEnregistree = false;
    await Trousseau.retirer(Trousseau.jetonDAcces);
    await Trousseau.retirer(Trousseau.jetonDeRafraichissement);
    _etat = Etat.dehors;
    notifyListeners();
  }

  void _adopter(ClientAPI client, Auth service, Uri base) {
    api = client;
    auth = service;
    // Le crochet réenregistre les jetons quand ils tournent ; sans lui le trousseau
    // garderait un jeton périmé et la prochaine ouverture échouerait sans raison visible.
    client.auRenouvellement = (jetons) {
      Trousseau.poser(jetons.acces, Trousseau.jetonDAcces);
      Trousseau.poser(jetons.rafraichissement, Trousseau.jetonDeRafraichissement);
    };
    // La première organisation ouverte fait la courante ; sans en-tête, le serveur
    // retiendrait la plus ancienne et on lirait les données d'une équipe en en
    // affichant une autre.
    _organisation ??= service.organisations.isEmpty ? null : service.organisations.first;
    client.poserLOrganisation(_organisation);
  }

  Future<void> _pendant(Future<void> Function() corps) async {
    _occupe = true;
    _erreur = null;
    notifyListeners();
    try {
      await corps();
    } on Object catch (e) {
      _erreur = '$e';
    } finally {
      _occupe = false;
      notifyListeners();
    }
  }

  Future<void> _enregistrer(ClientAPI client, Uri base) async {
    await Trousseau.poser(base.toString(), Trousseau.serveur);
    await Trousseau.poser(email, Trousseau.email);
    final jetons = client.jetons;
    if (jetons == null) return;
    await Trousseau.poser(jetons.acces, Trousseau.jetonDAcces);
    await Trousseau.poser(jetons.rafraichissement, Trousseau.jetonDeRafraichissement);
    _sessionEnregistree = true;
  }
}
