import 'dart:convert';

import '../modeles/contenus.dart';
import 'package:flutter_timezone/flutter_timezone.dart';

import 'api.dart';
import 'auth.dart';

/// Une organisation dont on est membre.
class Organisation {
  const Organisation({
    required this.id,
    required this.nom,
    required this.slug,
    required this.role,
  });

  factory Organisation.depuisJson(Map<String, dynamic> j) => Organisation(
        id: '${j['id']}',
        nom: '${j['name']}',
        slug: '${j['slug']}',
        role: '${j['role']}',
      );

  final String id;
  final String nom;
  final String slug;
  final String role;
}

/// Un calendrier de l'utilisateur.
class Calendrier {
  const Calendrier({
    required this.id,
    required this.nom,
    required this.couleur,
    required this.parDefaut,
    required this.partage,
    this.proprietaire,
    this.peutEcrireBrut,
  });

  factory Calendrier.depuisJson(Map<String, dynamic> j) => Calendrier(
        id: '${j['id']}',
        nom: '${j['name']}',
        couleur: '${j['color']}',
        parDefaut: j['is_default'] == true,
        partage: j['is_shared'] == true,
        proprietaire: j['owner_name'] as String?,
        peutEcrireBrut: j['can_write'] as bool?,
      );

  final String id;
  final String nom;
  final String couleur;
  final bool parDefaut;
  final bool partage;
  final String? proprietaire;
  final bool? peutEcrireBrut;

  /// Un calendrier partagé par quelqu'un d'autre peut être en lecture seule. Proposer d'y
  /// écrire ferait échouer l'enregistrement après que l'utilisateur a tout saisi — le pire
  /// moment pour apprendre qu'on n'avait pas le droit.
  ///
  /// Le champ est absent d'un serveur antérieur : on retombe alors sur « oui », qui était
  /// le comportement d'avant. Refuser par défaut priverait d'écriture sur un serveur
  /// parfaitement fonctionnel.
  bool get inscriptible => peutEcrireBrut ?? true;
}

/// D'où vient le titre d'une ligne, et s'il y en a un.
///
/// La distinction se voit à l'écran : un événement qu'on n'a pas su ouvrir ne doit pas se
/// confondre avec un événement sans titre, ni disparaître. Quatre provenances, parce que
/// les aplatir ferait passer une clé manquante pour un élément mal rempli.
enum ProvenanceDuTitre {
  /// Ouvert avec la clé de l'organisation.
  dechiffre,

  /// Rendu en clair par le serveur — une réservation prise depuis un lien, un calendrier
  /// externe abonné. Ce n'est pas une fuite : ces libellés sont publics par nature.
  enClair,

  /// Scellé, et la clé n'a pas ouvert. Un trou visible vaut mieux qu'une ligne absente :
  /// l'heure est occupée, l'utilisateur doit le voir.
  illisible,

  sansTitre,
}

/// Une ligne d'agenda, contenu ouvert quand on a pu.
class LigneDAgenda {
  const LigneDAgenda({
    required this.id,
    required this.evenement,
    required this.debut,
    required this.fin,
    required this.journeeEntiere,
    required this.lectureSeule,
    required this.provenance,
    required this.titre,
    required this.source,
    this.lieu,
  });

  final String id;

  /// L'identifiant de l'événement, quand la ligne en est un.
  ///
  /// Absent d'une occurrence de série développée par le serveur, et d'un créneau venu d'un
  /// calendrier externe : ces lignes-là s'affichent mais ne se modifient pas.
  final String? evenement;
  final DateTime debut;
  final DateTime fin;
  final bool journeeEntiere;
  final bool lectureSeule;
  final ProvenanceDuTitre provenance;
  final String titre;
  final String? lieu;
  final String source;
}

/// Le détail d'un événement, tel que le serveur le rend, contenu ouvert quand on a pu.
class DetailDEvenement {
  const DetailDEvenement({
    required this.id,
    required this.calendrier,
    required this.debut,
    required this.fin,
    required this.fuseau,
    required this.journeeEntiere,
    this.contenu,
  });

  final String id;
  final String calendrier;
  final DateTime debut;
  final DateTime fin;
  final String fuseau;
  final bool journeeEntiere;
  final ContenuDEvenement? contenu;
}

/// Lit l'agenda et ouvre ce qui peut l'être.
class Agenda {
  const Agenda({required this.api, required this.auth});

  final ClientAPI api;
  final Auth auth;

  Future<List<Organisation>> organisations() async {
    final brutes = await api.obtenir<List<dynamic>>('v1/me/organizations');
    return brutes
        .whereType<Map<String, dynamic>>()
        .map(Organisation.depuisJson)
        .toList();
  }

  Future<List<Calendrier>> calendriers() async {
    final brutes = await api.obtenir<List<dynamic>>('v1/me/calendars');
    return brutes.whereType<Map<String, dynamic>>().map(Calendrier.depuisJson).toList();
  }

  /// L'agenda entre deux dates.
  ///
  /// La fenêtre est bornée par le serveur à 366 jours — un événement récurrent développé
  /// sur une plage illimitée serait un déni de service. On demande donc une fenêtre
  /// étroite, et on la déplace, plutôt que de tout charger.
  Future<List<LigneDAgenda>> lignes({
    required DateTime de,
    required DateTime a,
    required String organisation,
  }) async {
    final brutes = await api.obtenir<List<dynamic>>('v1/me/calendar/agenda', {
      'from': isoPourLeServeur(de),
      'to': isoPourLeServeur(a),
    });

    final resultat = <LigneDAgenda>[];
    for (final brute in brutes.whereType<Map<String, dynamic>>()) {
      var provenance = ProvenanceDuTitre.sansTitre;
      var titre = '';
      String? lieu;

      final scelle = brute['content'];
      if (scelle is String && scelle.isNotEmpty) {
        final clair = await auth.ouvrir(scelle, organisation: organisation);
        final contenu =
            clair == null ? null : ContenuDEvenement.depuisJson(utf8.decode(clair));
        if (contenu == null) {
          provenance = ProvenanceDuTitre.illisible;
        } else {
          provenance = ProvenanceDuTitre.dechiffre;
          titre = contenu.title;
          lieu = contenu.location.isEmpty ? null : contenu.location;
        }
      } else {
        final enClair = brute['title'];
        if (enClair is String && enClair.isNotEmpty) {
          provenance = ProvenanceDuTitre.enClair;
          titre = enClair;
        }
      }

      final debut = DateTime.parse('${brute['start']}').toLocal();
      final lectureSeule = brute['read_only'] == true;
      final evenement = brute['event_id'] as String?;
      resultat.add(LigneDAgenda(
        // Une ligne d'agenda n'a pas toujours d'identifiant d'événement : une occurrence
        // de série ou un créneau externe n'en portent pas. La date de début complète la
        // clé, sinon deux lignes distinctes se confondraient dans la liste.
        id: '${evenement ?? brute['source']}-${debut.millisecondsSinceEpoch}',
        evenement: lectureSeule ? null : evenement,
        debut: debut,
        fin: DateTime.parse('${brute['end']}').toLocal(),
        journeeEntiere: brute['all_day'] == true,
        lectureSeule: lectureSeule,
        provenance: provenance,
        titre: titre,
        lieu: lieu,
        source: '${brute['source']}',
      ));
    }
    resultat.sort((a, b) => a.debut.compareTo(b.debut));
    return resultat;
  }

  /// Crée un événement. Le contenu est scellé ici ; les heures partent en clair.
  ///
  /// Ce n'est pas une concession : sans les heures, le serveur ne saurait ni répondre
  /// « occupé » à un lien de disponibilité, ni envoyer un rappel. Il apprend qu'un créneau
  /// est pris, jamais par quoi.
  Future<String> creerUnEvenement({
    required String titre,
    String description = '',
    String lieu = '',
    required DateTime debut,
    required DateTime fin,
    required bool journeeEntiere,
    required String calendrier,
    required String organisation,
    String? fuseau,
  }) async {
    final scelle = await _sceller(titre, description, lieu, organisation);
    final json = await api.envoyer<Map<String, dynamic>>(
      'POST',
      'v1/me/calendar/events',
      {
        'calendar_id': calendrier,
        'start_at': isoPourLeServeur(debut),
        'end_at': isoPourLeServeur(fin),
        // Le fuseau de l'appareil : c'est celui dans lequel l'utilisateur a lu les heures
        // qu'il vient de choisir. En envoyer un autre décalerait ce qu'il a sous les yeux.
        'timezone': fuseau ?? await fuseauCourant(),
        'all_day': journeeEntiere,
        'content': scelle,
      },
    );
    return '${json['id']}';
  }

  /// Le détail d'un événement, contenu ouvert.
  ///
  /// L'agenda n'en donne que ce qu'il faut pour l'afficher ; modifier demande le reste —
  /// le calendrier auquel il appartient, la description, le fuseau dans lequel il a été
  /// posé.
  Future<DetailDEvenement> evenement(String id, {required String organisation}) async {
    final j = await api.obtenir<Map<String, dynamic>>('v1/me/calendar/events/$id');
    ContenuDEvenement? contenu;
    final scelle = j['content'];
    if (scelle is String && scelle.isNotEmpty) {
      final clair = await auth.ouvrir(scelle, organisation: organisation);
      if (clair != null) contenu = ContenuDEvenement.depuisJson(utf8.decode(clair));
    }
    return DetailDEvenement(
      id: '${j['id']}',
      calendrier: '${j['calendar_id']}',
      debut: DateTime.parse('${j['start_at']}').toLocal(),
      fin: DateTime.parse('${j['end_at']}').toLocal(),
      fuseau: '${j['timezone']}',
      journeeEntiere: j['all_day'] == true,
      contenu: contenu,
    );
  }

  /// Modifie un événement.
  ///
  /// Le corps est envoyé **entier**, jamais champ par champ : cette route remplace, et
  /// omettre un champ le ramènerait à sa valeur par défaut sans un mot. C'est arrivé.
  ///
  /// Comme à la création, le contenu est scellé vers la clé **courante** : un événement
  /// corrigé après une rotation redevient lisible par tous, ce qui est l'effet recherché.
  Future<void> modifierUnEvenement(
    String id, {
    required String titre,
    required String description,
    required String lieu,
    required DateTime debut,
    required DateTime fin,
    required bool journeeEntiere,
    required String fuseau,
    required String calendrier,
    required String organisation,
  }) async {
    final scelle = await _sceller(titre, description, lieu, organisation);
    await api.envoyerSansReponse('PUT', 'v1/me/calendar/events/$id', {
      'calendar_id': calendrier,
      'start_at': isoPourLeServeur(debut),
      'end_at': isoPourLeServeur(fin),
      'timezone': fuseau,
      'all_day': journeeEntiere,
      'content': scelle,
    });
  }

  Future<void> supprimerUnEvenement(String id) =>
      api.envoyerSansReponse('DELETE', 'v1/me/calendar/events/$id');

  Future<String> _sceller(
    String titre,
    String description,
    String lieu,
    String organisation,
  ) async {
    final clair = utf8.encode(jsonEncode(
      ContenuDEvenement(title: titre, description: description, location: lieu).versJson(),
    ));
    return auth.sceller(clair, organisation: organisation);
  }

  /// Le fuseau de l'appareil, sous la forme que le serveur attend.
  ///
  /// `DateTime.now().timeZoneName` rend l'**abréviation** — « CEST » — là où le serveur
  /// veut un identifiant IANA — « Europe/Zurich ». Les confondre ne lève pas d'erreur :
  /// l'événement s'enregistre, et se relit dans un autre fuseau que celui où il a été
  /// posé. Il faut donc demander l'identifiant à la plateforme.
  static Future<String> fuseauCourant() async {
    try {
      return await FlutterTimezone.getLocalTimezone();
    } on Object {
      // Plutôt UTC qu'une abréviation ambiguë : au moins l'erreur est franche et connue.
      return 'UTC';
    }
  }

  /// Le serveur attend de l'ISO 8601 avec fuseau. `toIso8601String` d'une date locale n'en
  /// porte aucun : le serveur la lirait alors comme de l'UTC, et tout l'agenda glisserait
  /// du décalage horaire — sans erreur, juste faux.
  static String isoPourLeServeur(DateTime d) => d.toUtc().toIso8601String();
}
