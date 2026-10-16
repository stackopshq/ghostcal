import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../modeles/adresse.dart';
import 'api.dart';
import 'auth.dart';
import 'erreurs.dart';
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
  /// Le transport, pour les témoins.
  ///
  /// Même couture que `ClientAPI`, et pour la même raison : sans elle, tout ce que cette
  /// classe fait du réseau — dont la sonde qui juge l'adresse — ne s'éprouve qu'avec un
  /// vrai serveur en face.
  Session({http.Client? client}) : _transport = client;

  final http.Client? _transport;

  Etat _etat = Etat.dehors;
  bool _occupe = false;
  Object? _erreur;
  ErreurDAuth? _raisonDuCoffre;

  /// L'adresse et l'e-mail saisis, conservés entre deux lancements : les retaper à chaque
  /// fois serait la première friction d'une application qu'on ouvre dix fois par jour.
  String serveur = '';
  String email = '';

  ClientAPI? api;
  Auth? auth;

  /// Run at sign-out, before the tokens go: stops what works on the session's behalf in
  /// the background (the booking reminders).
  Future<void> Function()? avantDeSortir;
  String? _organisation;
  bool _sessionEnregistree = false;

  Etat get etat => _etat;
  bool get occupe => _occupe;
  /// The last failure, as raised: screens turn it into a sentence with `lisible`.
  Object? get erreur => _erreur;
  ErreurDAuth? get raisonDuCoffre => _raisonDuCoffre;
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
  void debugPoserEtat(Etat etat, {ErreurDAuth? raison}) {
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

  /// Le compte réclame un second facteur, et l'écran doit ouvrir un champ.
  ///
  /// Un état à part, pas un message d'erreur : `_pendant` transforme toute
  /// exception en texte affiché, et ce texte-là n'aurait donné aucune issue à
  /// quelqu'un dont le mot de passe est pourtant bon.
  SecondFacteurRequis? _secondFacteur;
  SecondFacteurRequis? get secondFacteur => _secondFacteur;

  Future<void> seConnecter({required String motDePasse, String? codeTotp}) async {
    final base = AdresseDeServeur.normaliser(serveur);
    if (base == null) {
      _erreur = const AdresseInvalide();
      notifyListeners();
      return;
    }
    await _pendant(() async {
      final client = ClientAPI(base: base, client: _transport);
      final service = Auth(client);
      final ErreurDAuth? echecDuCoffre;
      try {
        echecDuCoffre = await service.seConnecter(
          email: email,
          motDePasse: motDePasse,
          codeTotp: codeTotp,
        );
      } on SecondFacteurRequis catch (e) {
        // Ni une panne ni un refus : une étape de plus. On garde l'exigence et
        // on ne touche ni à l'état ni au client — l'écran va redemander.
        _secondFacteur = e;
        return;
      }
      _secondFacteur = null;

      // L'adresse authentifie — elle ne sert pas forcément le reste.
      //
      // Relevé sur `cal.ghostsuite.cloud` : l'API y vit sous `/api`, et le proxy laisse
      // passer `/v1/auth/*` sans préfixe. La connexion réussissait, le coffre s'ouvrait,
      // puis **tous** les écrans répondaient 404 — « Le serveur a répondu 404 » sur
      // l'agenda, ce qui est exact et ne désigne rien.
      //
      // La base n'était donc éprouvée que par les deux routes qui, précisément, ne
      // suffisent pas à la juger. Une requête de plus, sur un chemin `v1/me/*`, tranche
      // à la porte : un 404 ici ne peut pas être une ressource absente, puisque tout
      // compte authentifié a au moins une organisation.
      //
      // Posée ici et non dans `reprendre` : c'est à la saisie que l'erreur se commet, et
      // une base refusée ici n'est jamais enregistrée. L'ajouter au retour de session
      // coûterait un aller-retour à chaque ouverture, pour rattraper une faute qui ne
      // peut plus se produire.
      try {
        await client.obtenir<List<dynamic>>('v1/me/organizations');
      } on ErreurAPI catch (e) {
        if (e.statut == 404) throw const AdresseSansApi();
        rethrow;
      }

      _adopter(client, service, base);
      _etat = echecDuCoffre == null ? Etat.ouvert : Etat.coffreFerme;
      _raisonDuCoffre = echecDuCoffre;
      await _enregistrer(client, base);
    });
  }

  /// Abandonne la demande de second facteur — le bouton « revenir » de l'écran.
  void oublierLeSecondFacteur() {
    if (_secondFacteur == null) return;
    _secondFacteur = null;
    notifyListeners();
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
    final client = ClientAPI(base: base, client: _transport)
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
        _erreur = const SessionExpiree();
      } else {
        _erreur = e;
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
    try {
      await avantDeSortir?.call();
    } on Object catch (e) {
      debugPrint('ghostcal.session: sign-out hook failed: $e');
    }
    await auth?.revoquer();
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
    client.relireLesJetons = Trousseau.jetons;
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
      _erreur = e;
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
