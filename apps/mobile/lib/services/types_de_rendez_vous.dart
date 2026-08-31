import 'api.dart';

/// Un type de rendez-vous : ce qu'on propose à réserver.
///
/// **Rien n'est chiffré ici, et c'est voulu** — cette page est publique. Le titre, la durée
/// et les questions sont lus par des inconnus qui n'ont aucune clé ; les sceller rendrait
/// la réservation impossible. Ce qui est scellé, ce sont les réponses de l'invité, une fois
/// qu'il a réservé.
///
/// La classe garde le JSON brut à côté des champs qu'elle expose, et la raison est
/// importante : **la route de mise à jour est un `PUT` qui attend l'objet complet.**
/// N'envoyer que le champ modifié remettrait les autres à leur valeur par défaut — un
/// utilisateur qui coupe un créneau depuis son téléphone perdrait ses tampons, son préavis
/// et ses questions sans qu'aucune erreur ne le signale. Il ne s'en apercevrait qu'à la
/// prochaine réservation, ou jamais.
class TypeDeRendezVous {
  const TypeDeRendezVous({
    required this.id,
    required this.slugDOrganisation,
    required this.slug,
    required this.titre,
    required this.duree,
    required this.actif,
    required this.brut,
    this.description,
  });

  factory TypeDeRendezVous.depuisJson(Map<String, dynamic> j) => TypeDeRendezVous(
        id: '${j['id']}',
        slugDOrganisation: '${j['organization_slug']}',
        slug: '${j['slug']}',
        titre: '${j['title']}',
        description: j['description'] as String?,
        duree: (j['duration_min'] as num?)?.toInt() ?? 0,
        actif: j['active'] == true,
        brut: j,
      );

  final String id;
  final String slugDOrganisation;
  final String slug;
  final String titre;
  final String? description;
  final int duree;
  final bool actif;

  /// L'objet tel que le serveur l'a rendu. Conservé pour pouvoir le lui **renvoyer
  /// entier**, y compris les champs que cet écran n'affiche pas et ne comprend pas.
  final Map<String, dynamic> brut;
}

/// Les types de rendez-vous, et ce qu'on peut en faire depuis un téléphone.
///
/// Volontairement partiel : créer un type demande une quinzaine de réglages — intervalles,
/// tampons, préavis, fenêtre de réservation, questions — qui se règlent bien à un clavier
/// et mal à un pouce. Ce qu'on fait en mobilité, c'est vérifier ce qui est ouvert, partager
/// un lien, et couper un créneau qu'on ne veut plus.
class TypesDeRendezVous {
  const TypesDeRendezVous({required this.api});

  final ClientAPI api;

  Future<List<TypeDeRendezVous>> lister() async {
    final brutes = await api.obtenir<List<dynamic>>('v1/me/event-types');
    return ordonner(
      brutes.whereType<Map<String, dynamic>>().map(TypeDeRendezVous.depuisJson).toList(),
    );
  }

  /// Les actifs d'abord — c'est ce qu'on vient vérifier. À l'intérieur, l'ordre
  /// alphabétique, stable d'une lecture à l'autre.
  static List<TypeDeRendezVous> ordonner(List<TypeDeRendezVous> types) {
    final copie = [...types];
    copie.sort((a, b) {
      if (a.actif != b.actif) return a.actif ? -1 : 1;
      return a.titre.toLowerCase().compareTo(b.titre.toLowerCase());
    });
    return copie;
  }

  /// Ouvre ou ferme un type, **en renvoyant tout le reste inchangé**.
  ///
  /// Le corps repart du JSON reçu : c'est la seule façon de ne pas perdre un champ que
  /// cette version du client ignore. Un client plus ancien que le serveur écraserait
  /// sinon les réglages ajoutés depuis.
  Future<void> basculer(TypeDeRendezVous type, {required bool actif}) {
    final corps = Map<String, dynamic>.from(type.brut)..['active'] = actif;
    // Le serveur rend ces champs mais ne les accepte pas en écriture : les renvoyer ferait
    // échouer la requête sur une validation, pour des valeurs qu'on ne modifie pas.
    for (final lecture in ['id', 'organization_slug', 'slug', 'description']) {
      corps.remove(lecture);
    }
    return api.envoyerSansReponse('PUT', 'v1/me/event-types/${type.id}', corps);
  }

  Future<void> supprimer(String id) =>
      api.envoyerSansReponse('DELETE', 'v1/me/event-types/$id');

  /// L'adresse publique où l'on réserve ce type.
  ///
  /// Construite depuis l'adresse du serveur que l'utilisateur a saisie, et non depuis une
  /// constante : chaque client a sa propre instance, et un lien vers le mauvais domaine ne
  /// mènerait nulle part — sans qu'aucune erreur ne le signale, puisque c'est le
  /// destinataire qui le découvrirait.
  static Uri? lienPublic(TypeDeRendezVous type, {required String serveur}) {
    final base = Uri.tryParse(serveur);
    if (base == null || base.host.isEmpty) return null;
    return base.replace(path: '/${type.slugDOrganisation}/${type.slug}');
  }
}
