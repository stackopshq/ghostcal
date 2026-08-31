import 'dart:convert';

import '../modeles/contenus.dart';
import 'api.dart';
import 'auth.dart';

/// D'où vient le nom de l'invité, et s'il y en a un.
///
/// Le partage entre clair et scellé est plus subtil ici qu'ailleurs :
///
/// - le **nom du type de rendez-vous** est en clair : le visiteur l'a lu sur la page de
///   réservation, il n'a jamais été secret ;
/// - l'**adresse e-mail** aussi — le serveur doit envoyer confirmations et rappels ;
/// - le **nom de l'invité** est nul pour une réservation prise depuis une page publique :
///   le vrai nom est scellé. Le traiter comme toujours présent afficherait « Sans nom » là
///   où le nom existe, chiffré, juste à côté.
enum NomDInvite {
  enClair,
  dechiffre,

  /// Scellé, non ouvert. L'écran affiche alors l'adresse, qui est en clair : mieux vaut
  /// identifier la personne par son adresse que ne rien montrer du tout.
  illisible,
  inconnu,
}

enum StatutDeReunion {
  confirmee,
  annulee,
  autre;

  static StatutDeReunion depuis(String brut) => switch (brut) {
        'confirmed' => StatutDeReunion.confirmee,
        'cancelled' => StatutDeReunion.annulee,
        _ => StatutDeReunion.autre,
      };
}

/// Une réunion, contenu ouvert quand on a pu.
class Reunion {
  const Reunion({
    required this.id,
    required this.intitule,
    required this.debut,
    required this.fin,
    required this.statut,
    required this.courriel,
    required this.fuseau,
    required this.provenanceDuNom,
    required this.nom,
    required this.reponses,
    this.lieu,
    this.adresse,
    this.notes,
  });

  final String id;
  final String intitule;
  final DateTime debut;
  final DateTime fin;
  final StatutDeReunion statut;

  /// Vide quand le serveur ne le rend pas. L'écran retombe alors sur le nom déchiffré, et
  /// à défaut ne montre rien plutôt qu'une ligne vide qui ressemblerait à un défaut.
  final String courriel;
  final String fuseau;
  final String? lieu;
  final Uri? adresse;
  final NomDInvite provenanceDuNom;
  final String nom;
  final List<MapEntry<String, String>> reponses;
  final String? notes;
}

/// À venir, ou passées.
///
/// Le serveur tranche : demander les deux et filtrer ici obligerait à télécharger un
/// historique entier pour afficher trois lignes.
enum PorteeDesReunions {
  aVenir('upcoming'),
  passees('past');

  const PorteeDesReunions(this.valeur);
  final String valeur;
}

/// Lire et annuler les réunions.
class Reunions {
  const Reunions({required this.api, required this.auth});

  final ClientAPI api;
  final Auth auth;

  Future<List<Reunion>> lister(
    PorteeDesReunions portee, {
    required String organisation,
  }) async {
    final brutes = await api.obtenir<List<dynamic>>(
      'v1/me/meetings',
      {'scope': portee.valeur},
    );

    final resultat = <Reunion>[];
    for (final brute in brutes.whereType<Map<String, dynamic>>()) {
      var provenance = NomDInvite.inconnu;
      var nom = '';
      var reponses = <MapEntry<String, String>>[];
      String? notes;

      final enClair = brute['invitee_name'];
      if (enClair is String && enClair.isNotEmpty) {
        provenance = NomDInvite.enClair;
        nom = enClair;
      }

      final scelle = brute['invitee_private'];
      if (scelle is String && scelle.isNotEmpty) {
        final clair = await auth.ouvrir(scelle, organisation: organisation);
        final contenu =
            clair == null ? null : ContenuDInvite.depuisJson(utf8.decode(clair));
        if (contenu != null) {
          if (contenu.name.isNotEmpty) {
            provenance = NomDInvite.dechiffre;
            nom = contenu.name;
          }
          reponses = contenu.reponsesTriees;
          notes = contenu.notes.isEmpty ? null : contenu.notes;
        } else if (provenance == NomDInvite.inconnu) {
          // Illisible seulement si rien d'autre ne nomme la personne : un nom rendu en
          // clair par le serveur reste préférable à un aveu d'échec.
          provenance = NomDInvite.illisible;
        }
      }

      final adresse = brute['meeting_url'];
      resultat.add(Reunion(
        id: '${brute['id']}',
        intitule: '${brute['event_title']}',
        debut: DateTime.parse('${brute['start_at']}').toLocal(),
        fin: DateTime.parse('${brute['end_at']}').toLocal(),
        statut: StatutDeReunion.depuis('${brute['status']}'),
        // Optionnel **par prudence**, alors que le serveur le rend toujours aujourd'hui :
        // un mode où l'identité de l'invité est scellée est décidé (ADR-0038). Avec un
        // champ obligatoire, l'écran entier deviendrait vide chez qui choisit ce mode,
        // sans rapport apparent avec la cause.
        courriel: brute['invitee_email'] as String? ?? '',
        fuseau: '${brute['invitee_timezone']}',
        lieu: brute['location'] as String?,
        adresse: adresse is String ? Uri.tryParse(adresse) : null,
        provenanceDuNom: provenance,
        nom: nom,
        reponses: reponses,
        notes: notes,
      ));
    }
    return ordonner(resultat, portee);
  }

  /// À venir : la plus proche d'abord. Passées : la plus récente d'abord — on remonte le
  /// temps quand on cherche dans un historique.
  static List<Reunion> ordonner(List<Reunion> reunions, PorteeDesReunions portee) {
    final copie = [...reunions];
    copie.sort((a, b) => portee == PorteeDesReunions.aVenir
        ? a.debut.compareTo(b.debut)
        : b.debut.compareTo(a.debut));
    return copie;
  }

  Future<void> annuler(String id) =>
      api.envoyerSansReponse('POST', 'v1/me/meetings/$id/cancel');
}
