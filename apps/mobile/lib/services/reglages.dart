import 'api.dart';

// ─── Disponibilités ───

/// Une plage récurrente : « lundi de 9 h à 12 h ».
class RegleDHoraire {
  const RegleDHoraire({required this.jourServeur, required this.debut, required this.fin});

  factory RegleDHoraire.depuisJson(Map<String, dynamic> j) => RegleDHoraire(
        jourServeur: (j['weekday'] as num?)?.toInt() ?? -1,
        debut: '${j['start']}',
        fin: '${j['end']}',
      );

  /// La convention du **serveur** : 0 = lundi.
  ///
  /// `DateTime` de Dart compte 1 = lundi, et Java 1 = dimanche. Confondre les trois
  /// décalerait tout l'horaire d'un jour, silencieusement : l'écran afficherait un horaire
  /// cohérent, mais pas celui qui gouverne les réservations. Personne ne le remarquerait
  /// avant qu'un invité réserve un dimanche.
  final int jourServeur;
  final String debut;
  final String fin;

  static const _jours = [
    'lundi',
    'mardi',
    'mercredi',
    'jeudi',
    'vendredi',
    'samedi',
    'dimanche',
  ];

  /// Le nom du jour, ou « ? ».
  ///
  /// La valeur est vérifiée **avant** la conversion, jamais ramenée par modulo : un
  /// `weekday` de 42 qui s'afficherait « lundi » serait une valeur fausse présentée avec
  /// l'assurance d'une vraie. Un point d'interrogation se remarque ; un mauvais jour, non.
  String get jour =>
      jourServeur >= 0 && jourServeur < _jours.length ? _jours[jourServeur] : '?';
}

class Horaire {
  const Horaire({
    required this.id,
    required this.nom,
    required this.fuseau,
    required this.regles,
  });

  factory Horaire.depuisJson(Map<String, dynamic> j) => Horaire(
        id: '${j['id']}',
        nom: '${j['name']}',
        fuseau: '${j['timezone']}',
        regles: (j['rules'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(RegleDHoraire.depuisJson)
            .toList(),
      );

  final String id;
  final String nom;
  final String fuseau;
  final List<RegleDHoraire> regles;
}

// ─── Sondages ───

class Sondage {
  const Sondage({
    required this.id,
    required this.titre,
    required this.statut,
    required this.nombreDOptions,
    required this.nombreDeVotes,
  });

  factory Sondage.depuisJson(Map<String, dynamic> j) => Sondage(
        id: '${j['id']}',
        titre: '${j['title']}',
        statut: '${j['status']}',
        nombreDOptions: (j['option_count'] as num?)?.toInt() ?? 0,
        nombreDeVotes: (j['vote_count'] as num?)?.toInt() ?? 0,
      );

  final String id;
  final String titre;
  final String statut;
  final int nombreDOptions;
  final int nombreDeVotes;

  bool get ouvert => statut == 'open';
}

class OptionDeSondage {
  const OptionDeSondage({
    required this.id,
    required this.debut,
    required this.fin,
    required this.votes,
  });

  factory OptionDeSondage.depuisJson(Map<String, dynamic> j) => OptionDeSondage(
        id: '${j['id']}',
        debut: DateTime.parse('${j['start_at']}').toLocal(),
        fin: DateTime.parse('${j['end_at']}').toLocal(),
        votes: (j['votes'] as num?)?.toInt() ?? 0,
      );

  final String id;
  final DateTime debut;
  final DateTime fin;
  final int votes;
}

class Votant {
  const Votant({required this.nom, required this.courriel, required this.options});

  factory Votant.depuisJson(Map<String, dynamic> j) => Votant(
        nom: '${j['name']}',
        courriel: '${j['email']}',
        options: (j['option_ids'] as List? ?? const []).map((e) => '$e').toList(),
      );

  final String nom;
  final String courriel;
  final List<String> options;
}

class DetailDeSondage {
  const DetailDeSondage({
    required this.id,
    required this.titre,
    required this.duree,
    required this.statut,
    required this.options,
    required this.votants,
    this.optionRetenue,
  });

  factory DetailDeSondage.depuisJson(Map<String, dynamic> j) => DetailDeSondage(
        id: '${j['id']}',
        titre: '${j['title']}',
        duree: (j['duration_min'] as num?)?.toInt() ?? 0,
        statut: '${j['status']}',
        optionRetenue: j['finalized_option_id'] as String?,
        options: (j['options'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(OptionDeSondage.depuisJson)
            .toList(),
        votants: (j['voters'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(Votant.depuisJson)
            .toList(),
      );

  final String id;
  final String titre;
  final int duree;
  final String statut;
  final String? optionRetenue;
  final List<OptionDeSondage> options;
  final List<Votant> votants;

  bool get ouvert => statut == 'open';
}

// ─── Profil et équipe ───

class Profil {
  const Profil({
    required this.id,
    required this.courriel,
    required this.nom,
    required this.fuseau,
    required this.courrielVerifie,
    this.avatar,
  });

  factory Profil.depuisJson(Map<String, dynamic> j) => Profil(
        id: '${j['id']}',
        courriel: '${j['email']}',
        nom: '${j['name']}',
        fuseau: '${j['timezone']}',
        courrielVerifie: j['email_verified'] == true,
        avatar: j['avatar_url'] as String?,
      );

  final String id;
  final String courriel;
  final String nom;
  final String fuseau;
  final bool courrielVerifie;
  final String? avatar;
}

class Membre {
  const Membre({
    required this.id,
    required this.nom,
    required this.courriel,
    required this.role,
  });

  factory Membre.depuisJson(Map<String, dynamic> j) => Membre(
        id: '${j['user_id']}',
        nom: '${j['name']}',
        courriel: '${j['email']}',
        role: '${j['role']}',
      );

  final String id;
  final String nom;
  final String courriel;
  final String role;

  /// Le rôle, dit en français.
  ///
  /// Un rôle inconnu s'affiche **tel quel** plutôt que d'être masqué ou ramené à
  /// « membre » : un serveur plus récent peut en introduire, et taire le rôle de quelqu'un
  /// — ou le présenter comme moins puissant qu'il n'est — serait pire que l'afficher en
  /// anglais.
  String get roleLisible => switch (role) {
        'owner' => 'Propriétaire',
        'admin' => 'Administrateur',
        'member' => 'Membre',
        _ => role,
      };
}

/// Les écrans de réglage : disponibilités, sondages, profil, équipe.
///
/// Un seul service pour quatre lectures qui n'ont rien de commun sinon d'être des
/// réglages. Les séparer en quatre aurait multiplié la cérémonie sans rien clarifier :
/// aucun ne porte d'état, tous ne font qu'un appel.
class Reglages {
  const Reglages({required this.api});

  final ClientAPI api;

  Future<List<Horaire>> horaires() async {
    final brutes = await api.obtenir<List<dynamic>>('v1/me/schedules');
    return brutes.whereType<Map<String, dynamic>>().map(Horaire.depuisJson).toList();
  }

  Future<List<Sondage>> sondages() async {
    final brutes = await api.obtenir<List<dynamic>>('v1/me/polls');
    return brutes.whereType<Map<String, dynamic>>().map(Sondage.depuisJson).toList();
  }

  Future<DetailDeSondage> sondage(String id) async =>
      DetailDeSondage.depuisJson(await api.obtenir('v1/me/polls/$id'));

  /// Retient un créneau : le sondage se ferme et l'événement se crée côté serveur.
  Future<DetailDeSondage> finaliser(String id, {required String option}) async =>
      DetailDeSondage.depuisJson(
        await api.envoyer('POST', 'v1/me/polls/$id/finalize', {'option_id': option}),
      );

  Future<void> annulerLeSondage(String id) =>
      api.envoyerSansReponse('DELETE', 'v1/me/polls/$id');

  Future<Profil> profil() async => Profil.depuisJson(await api.obtenir('v1/me/profile'));

  /// Enregistre le profil.
  ///
  /// `avatar_url` est envoyé **même quand il est nul**, et c'est tout l'intérêt de le
  /// construire à la main : la route est un `PUT` qui remplace. Omettre le champ demande
  /// « ne touche pas » ; l'envoyer à `null` demande « efface ». L'écran qui retire une
  /// photo exprime la seconde, et un encodeur qui saute les nuls exprimerait la première.
  ///
  /// `email` n'en fait pas partie : le changer demande une vérification, et cette route ne
  /// la déclenche pas.
  Future<Profil> enregistrerLeProfil({
    required String nom,
    required String fuseau,
    required String? avatar,
  }) async =>
      Profil.depuisJson(await api.envoyer('PUT', 'v1/me/profile', {
        'name': nom,
        'timezone': fuseau,
        'avatar_url': avatar,
      }));

  Future<List<Membre>> membres() async {
    final brutes = await api.obtenir<List<dynamic>>('v1/me/organization/members');
    return brutes.whereType<Map<String, dynamic>>().map(Membre.depuisJson).toList();
  }

  /// Change le rôle d'un membre.
  ///
  /// Le serveur rend la liste à jour, qu'on réutilise plutôt que de relire : deux appels
  /// donneraient deux vérités possibles entre-temps.
  Future<List<Membre>> changerLeRole(String utilisateur, {required String role}) async {
    final brutes = await api.envoyer<List<dynamic>>(
      'PATCH',
      'v1/me/organization/members/$utilisateur',
      {'role': role},
    );
    return brutes.whereType<Map<String, dynamic>>().map(Membre.depuisJson).toList();
  }

  Future<void> retirerLeMembre(String utilisateur) =>
      api.envoyerSansReponse('DELETE', 'v1/me/organization/members/$utilisateur');
}
