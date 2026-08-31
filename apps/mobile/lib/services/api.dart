import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../modeles/adresse.dart';

/// Ce que le serveur rend quand il refuse.
///
/// Deux formes coexistent — une chaîne, ou une liste de validations — et les confondre
/// afficherait « Instance of 'List' » à l'utilisateur. Le message est ce qu'il lira ; il
/// mérite d'être extrait, pas deviné.
class ErreurAPI implements Exception {
  ErreurAPI(this.statut, this.message);

  final int statut;
  final String message;

  /// La session a expiré, par opposition à un refus de droits. Les deux se corrigent
  /// autrement : l'une demande de se reconnecter, l'autre n'a pas de remède côté client.
  bool get sessionExpiree => statut == 401;

  @override
  String toString() => message;
}

/// Les jetons d'une session.
class Jetons {
  const Jetons({required this.acces, required this.rafraichissement});

  final String acces;
  final String rafraichissement;
}

/// Le client HTTP du serveur GhostCal.
///
/// Porté depuis `APIClient.swift`, avec ses comportements — pas seulement ses routes :
///
/// - **le jeton de rafraîchissement tourne** : le serveur en rend un nouveau à chaque
///   usage, et garder l'ancien ferait échouer le suivant ;
/// - **une seule tentative de rafraîchissement** par appel, sinon un jeton définitivement
///   mort provoquerait une boucle ;
/// - **l'organisation courante voyage en en-tête** ; sans elle le serveur retient la plus
///   ancienne, ce qui ferait lire les données d'une équipe en en affichant une autre.
class ClientAPI {
  ClientAPI({required this.base, http.Client? client})
      : _client = client ?? http.Client();

  final Uri base;
  final http.Client _client;

  Jetons? _jetons;
  String? _organisation;

  /// Rappelé quand les jetons tournent, pour que la session les réenregistre. Sans ce
  /// crochet, le trousseau garderait un jeton périmé et la prochaine ouverture échouerait
  /// sans raison visible.
  void Function(Jetons)? auRenouvellement;

  Jetons? get jetons => _jetons;
  void poserLesJetons(Jetons? valeur) => _jetons = valeur;
  void poserLOrganisation(String? id) => _organisation = id;

  Future<T> obtenir<T>(String chemin, [Map<String, String> requete = const {}]) async {
    final corps = await _appeler('GET', chemin, requete: requete);
    return _decoder<T>(corps);
  }

  Future<T> envoyer<T>(String methode, String chemin, Object? corps) async {
    final reponse = await _appeler(methode, chemin, corps: corps);
    return _decoder<T>(reponse);
  }

  /// Pour les routes qui rendent 204. Décoder leur corps vide lèverait une exception là
  /// où tout s'est bien passé.
  Future<void> envoyerSansReponse(String methode, String chemin, [Object? corps]) async {
    await _appeler(methode, chemin, corps: corps);
  }

  Future<String> _appeler(
    String methode,
    String chemin, {
    Map<String, String> requete = const {},
    Object? corps,
    bool dejaRafraichi = false,
  }) async {
    final url = base.replace(
      path: '${base.path}/$chemin'.replaceAll(RegExp(r'/+'), '/'),
      queryParameters: requete.isEmpty ? null : requete,
    );

    final entetes = <String, String>{
      if (corps != null) 'content-type': 'application/json',
      if (_jetons != null) 'authorization': 'Bearer ${_jetons!.acces}',
      'x-organization-id': ?_organisation,
    };

    final requeteHttp = http.Request(methode, url)..headers.addAll(entetes);
    if (corps != null) requeteHttp.body = jsonEncode(corps);

    final flux = await _client.send(requeteHttp);
    final reponse = await http.Response.fromStream(flux);

    if (reponse.statusCode == 401 && !dejaRafraichi && _jetons != null) {
      if (await _rafraichir()) {
        return _appeler(methode, chemin,
            requete: requete, corps: corps, dejaRafraichi: true);
      }
    }

    if (reponse.statusCode < 200 || reponse.statusCode >= 300) {
      throw ErreurAPI(reponse.statusCode, _messageDErreur(reponse));
    }
    return reponse.body;
  }

  /// Échange le jeton de rafraîchissement contre une paire neuve.
  ///
  /// Rend faux plutôt que de jeter : l'appelant décidera si la session est perdue. Un
  /// échec ici n'est pas toujours une erreur — un jeton simplement expiré demande une
  /// reconnexion, pas un message d'incident.
  Future<bool> _rafraichir() async {
    final jetons = _jetons;
    if (jetons == null) return false;
    try {
      final reponse = await _client.post(
        base.replace(path: '${base.path}/v1/auth/refresh'.replaceAll(RegExp(r'/+'), '/')),
        headers: const {'content-type': 'application/json'},
        body: jsonEncode({'refresh_token': jetons.rafraichissement}),
      );
      if (reponse.statusCode < 200 || reponse.statusCode >= 300) {
        _jetons = null;
        return false;
      }
      final json = jsonDecode(reponse.body) as Map<String, dynamic>;
      final acces = json['access_token'];
      // Le serveur fait tourner le jeton de rafraîchissement : garder l'ancien ferait
      // échouer le prochain renouvellement, et l'utilisateur serait déconnecté sans
      // comprendre pourquoi.
      final suivant = json['refresh_token'] ?? jetons.rafraichissement;
      if (acces is! String) return false;
      _jetons = Jetons(acces: acces, rafraichissement: '$suivant');
      auRenouvellement?.call(_jetons!);
      return true;
    } on Exception {
      // Réseau coupé : on ne détruit pas la session pour autant.
      return false;
    }
  }

  String _messageDErreur(http.Response reponse) {
    try {
      final json = jsonDecode(reponse.body);
      if (json is Map<String, dynamic>) {
        final detail = json['detail'] ?? json['error'] ?? json['message'];
        if (detail is String) return detail;
        // FastAPI rend une liste d'objets de validation. L'afficher telle quelle
        // donnerait « [{loc: [...], msg: ... }] » à l'utilisateur.
        if (detail is List && detail.isNotEmpty) {
          final premier = detail.first;
          if (premier is Map && premier['msg'] is String) return premier['msg'] as String;
        }
      }
    } on FormatException {
      // Un corps qui n'est pas du JSON : le statut reste plus utile que le contenu.
    }
    return 'Le serveur a répondu ${reponse.statusCode}.';
  }

  T _decoder<T>(String corps) {
    if (corps.isEmpty) return null as T;
    return jsonDecode(corps) as T;
  }
}

/// Fabrique un client depuis une adresse saisie, ou rend nul si elle n'en est pas une.
ClientAPI? clientPour(String adresse) {
  final base = AdresseDeServeur.normaliser(adresse);
  return base == null ? null : ClientAPI(base: base);
}
