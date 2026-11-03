import 'api.dart';

/// Un calendrier externe **connecté** : un compte CalDAV, iCloud, Google.
///
/// ─── La troisième source, et la dernière à être restée invisible ───
///
/// L'agenda a trois provenances étrangères aux calendriers de GhostCal : les
/// réservations, les abonnements ICS, et celle-ci. Les abonnements ont eu leur ligne
/// dans la colonne en 1.8.0 ; les comptes connectés, jamais. `git log -S` sur
/// `apps/mobile/` ne rendait pas un seul commit touchant `v1/me/calendar/connections` —
/// le client mobile n'a appelé cette route à aucune version, sur aucune plateforme.
///
/// Et comme le filtre de l'agenda est une liste de **masqués** et non d'autorisés, leurs
/// événements passaient quand même : le serveur les rend avec `source: "external"` et
/// `calendar_id` portant l'identifiant de la connexion. On voyait donc les rendez-vous
/// d'un agenda professionnel, dans la couleur d'accent faute de correspondance, sans son
/// nom nulle part et sans case pour les cacher. Exactement ce que la colonne latérale
/// décrit comme le prix de ce choix : « qui ajoute une source doit lui donner sa ligne
/// dans la colonne, pas seulement ses événements dans la grille ».
///
/// ─── Ce qu'on ne fait pas ici ───
///
/// **Connecter et déconnecter restent au web.** Connecter demande un mot de passe de
/// serveur, et déconnecter emporte les créneaux rapatriés. Ni l'un ni l'autre ne manque
/// à quelqu'un qui cherche simplement à voir son agenda de travail sur son Mac, et les
/// offrir à moitié — une saisie de mot de passe sans la découverte des calendriers que
/// le web propose — vaudrait moins que de ne rien offrir.
class Connexion {
  const Connexion({
    required this.id,
    required this.serveur,
    required this.identifiant,
    required this.couleur,
    required this.etat,
    this.nomDuCalendrier,
    this.dernierSynchro,
  });

  factory Connexion.depuisJson(Map<String, dynamic> j) => Connexion(
    id: '${j['id']}',
    serveur: '${j['server_url']}',
    identifiant: '${j['username']}',
    couleur: '${j['color']}',
    etat: '${j['status']}',
    nomDuCalendrier: j['calendar_name'] as String?,
    dernierSynchro: switch (j['last_synced_at']) {
      final String s => DateTime.tryParse(s)?.toLocal(),
      _ => null,
    },
  );

  final String id;

  /// L'adresse du serveur CalDAV et le compte qui s'y connecte. **Aucun mot de passe** :
  /// le serveur ne le rend pas, et c'est délibéré de sa part.
  final String serveur;
  final String identifiant;

  final String couleur;

  /// Ce que le serveur dit du dernier rapatriement. Valeur libre côté serveur : on ne
  /// s'en sert que pour signaler un ennui, jamais pour décider quoi que ce soit.
  final String etat;

  /// Le nom du calendrier distant. Peut manquer — un serveur CalDAV n'est pas tenu d'en
  /// donner un — et l'écran retombe alors sur l'identifiant du compte, qui dit au moins
  /// de qui il s'agit.
  final String? nomDuCalendrier;

  final DateTime? dernierSynchro;

  /// Comment nommer cette connexion à l'écran, sans jamais rendre une chaîne vide.
  ///
  /// Trois rangs : le nom du calendrier distant, puis le compte, puis l'hôte du serveur.
  /// Une ligne sans libellé serait une case à cocher qui ne dit pas ce qu'elle cache.
  String get libelle {
    final nom = nomDuCalendrier?.trim();
    if (nom != null && nom.isNotEmpty) return nom;
    final compte = identifiant.trim();
    if (compte.isNotEmpty) return compte;
    return Uri.tryParse(serveur)?.host ?? serveur;
  }

  /// Le compte ne se synchronise plus et attend qu'on le reconnecte.
  ///
  /// La base n'autorise que deux valeurs — `CheckConstraint("status IN ('active',
  /// 'needs_reauth')")` — et c'est `needs_reauth` que le serveur pose quand le
  /// rapatriement se heurte à une authentification refusée. Un mot de passe changé à
  /// l'autre bout suffit, et rien ne le dit à qui regarde son agenda : ce qui reste
  /// affiché vient du dernier rapatriement réussi, donc l'écran a l'air à jour.
  ///
  /// On teste « différent d'actif » plutôt que « égal à `needs_reauth` » : si le serveur
  /// se met un jour à poser un troisième état, il sera signalé plutôt que de passer
  /// pour sain. Se tromper dans ce sens fait regarder un compte qui va bien ; dans
  /// l'autre, il fait rater un agenda figé depuis des semaines.
  bool get enPanne => etat != 'active';
}

/// Les comptes connectés de l'utilisateur, sur `v1/me/calendar/connections`.
class Connexions {
  const Connexions({required this.api});

  final ClientAPI api;

  Future<List<Connexion>> lister() async {
    final brutes = await api.obtenir<List<dynamic>>(
      'v1/me/calendar/connections',
    );
    return brutes
        .whereType<Map<String, dynamic>>()
        .map(Connexion.depuisJson)
        .toList();
  }

  /// Recolore une connexion. `PATCH` et un seul champ : la couleur a été attribuée en
  /// faisant tourner une palette au moment de la connexion, et le seul moyen d'en
  /// changer était de déconnecter puis reconnecter — donc de ressaisir le mot de passe
  /// du serveur.
  Future<void> recolorer({required String id, required String couleur}) =>
      api.envoyerSansReponse('PATCH', 'v1/me/calendar/connections/$id', {
        'color': couleur,
      });

  /// Redemande tous les comptes tout de suite, sans attendre le travail de fond.
  ///
  /// Toutes, et non une seule : c'est le geste que le web offre, et celui qu'on veut
  /// quand on vient de modifier quelque chose à l'autre bout. Un échec sur un compte
  /// n'arrête pas les autres — le serveur rend le nombre de ceux qui ont abouti.
  Future<int> synchroniser() async {
    // Corps nul et non `{}` : la route ne lit aucune charge, et le web l'appelle les
    // mains vides. Envoyer un objet obligerait le serveur à l'accepter pour toujours.
    final brut = await api.envoyer<Map<String, dynamic>>(
      'POST',
      'v1/me/calendar/sync',
      null,
    );
    return switch (brut['synced']) {
      final int n => n,
      _ => 0,
    };
  }
}
