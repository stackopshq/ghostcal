import 'api.dart';

/// Un calendrier auquel on s'abonne, par son flux ICS.
///
/// ─── Ce que c'est, et ce que ce n'est pas ───
///
/// Un abonnement n'est **pas** un calendrier. Il ne vit pas dans `v1/me/calendars`, on
/// n'y écrit jamais, et son contenu appartient à quelqu'un d'autre : le serveur va
/// chercher le flux, en garde les événements, et les rend dans l'agenda avec
/// `source: "subscription"`. C'est l'agenda d'une équipe de foot, les jours fériés d'un
/// canton, le planning d'une salle.
///
/// Les deux se ressemblent assez pour qu'on les mélange — un nom, une couleur, des
/// événements, une case à cocher — et assez peu pour que les confondre fasse offrir
/// « Nouvel événement » sur un flux en lecture seule. Ils restent donc deux choses, et
/// c'est déjà le choix du serveur et du web.
///
/// ─── Pourquoi ce fichier n'existait pas ───
///
/// Le web pose ces abonnements depuis toujours, et l'API les expose en entier : lister,
/// ajouter, recolorer, rafraîchir, supprimer. L'application mobile n'en appelait
/// **aucune** — le mot « subscription » n'apparaissait nulle part dans `lib/`.
///
/// Ce que ça donnait est pire qu'une absence franche : comme le filtre des calendriers
/// est une liste de **masqués** et non une liste d'autorisés, les événements du flux
/// s'affichaient quand même. On voyait donc les rendez-vous d'un abonnement posé depuis
/// le web, dans une couleur qui n'était pas la sienne, sans sa case pour les cacher,
/// sans son nom nulle part, et sans moyen de l'enlever ni d'en ajouter un autre.
class Abonnement {
  const Abonnement({
    required this.id,
    required this.nom,
    required this.url,
    required this.couleur,
    required this.bloqueLesDisponibilites,
    required this.etat,
    this.derniereErreur,
    this.dernierSynchro,
  });

  factory Abonnement.depuisJson(Map<String, dynamic> j) => Abonnement(
    id: '${j['id']}',
    nom: '${j['name']}',
    url: '${j['url']}',
    couleur: '${j['color']}',
    bloqueLesDisponibilites: j['blocks_availability'] == true,
    etat: '${j['status']}',
    derniereErreur: j['last_error'] as String?,
    dernierSynchro: switch (j['last_synced_at']) {
      final String s => DateTime.tryParse(s)?.toLocal(),
      _ => null,
    },
  );

  final String id;
  final String nom;
  final String url;
  final String couleur;

  /// Un abonnement est informatif par défaut : il ne mange pas les créneaux qu'on offre
  /// à la réservation tant qu'on ne le demande pas.
  final bool bloqueLesDisponibilites;

  /// Ce que le serveur dit du dernier rapatriement. Une valeur libre côté serveur, donc
  /// on ne s'en sert que pour signaler un ennui, jamais pour décider quoi que ce soit.
  final String etat;
  final String? derniereErreur;
  final DateTime? dernierSynchro;

  /// Le flux a cessé de répondre. Ce qu'on affiche vient alors du dernier rapatriement
  /// réussi, et le taire laisserait croire à un agenda à jour.
  bool get enPanne => derniereErreur != null && derniereErreur!.isNotEmpty;
}

/// Les abonnements de l'utilisateur, sur `v1/me/calendar/subscriptions`.
class Abonnements {
  const Abonnements({required this.api});

  final ClientAPI api;

  Future<List<Abonnement>> lister() async {
    final brutes = await api.obtenir<List<dynamic>>(
      'v1/me/calendar/subscriptions',
    );
    return brutes
        .whereType<Map<String, dynamic>>()
        .map(Abonnement.depuisJson)
        .toList();
  }

  /// Ajoute un flux, et rend l'identifiant que le serveur lui a donné.
  ///
  /// L'URL n'est **pas** normalisée ici. Apple, Google et Outlook donnent des liens
  /// `webcal://`, un schéma qui n'a jamais existé ailleurs que dans les clients de
  /// bureau et qui désigne la même ressource en HTTPS ; le serveur le réécrit et rogne
  /// les espaces d'un copier-coller. Le refaire ici donnerait deux règles à tenir
  /// d'accord, et c'est la deuxième qui se trompe.
  ///
  /// Un flux injoignable rend un 422 **à la création** : le serveur le lit avant de
  /// l'enregistrer, plutôt que d'accepter une URL fausse et de la laisser échouer en
  /// silence dans un travail de fond. L'appelant doit donc montrer l'erreur.
  Future<String> ajouter({
    required String nom,
    required String url,
    required String couleur,
  }) async {
    final brut = await api.envoyer<Map<String, dynamic>>(
      'POST',
      'v1/me/calendar/subscriptions',
      {'name': nom.trim(), 'url': url.trim(), 'color': couleur},
    );
    return '${brut['id']}';
  }

  Future<void> supprimer(String id) =>
      api.envoyerSansReponse('DELETE', 'v1/me/calendar/subscriptions/$id');

  /// Redemande le flux tout de suite, sans attendre le travail de fond.
  Future<void> rafraichir(String id) => api.envoyerSansReponse(
    'POST',
    'v1/me/calendar/subscriptions/$id/refresh',
  );

  /// Recolore un abonnement. `PATCH` et un seul champ : le serveur exige qu'au moins un
  /// soit présent et laisse intact celui qu'on omet, donc recolorer ne vient pas
  /// réaffirmer un `blocks_availability` qu'on n'a pas lu.
  Future<void> recolorer({required String id, required String couleur}) =>
      api.envoyerSansReponse('PATCH', 'v1/me/calendar/subscriptions/$id', {
        'color': couleur,
      });
}
