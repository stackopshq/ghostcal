import 'dart:convert';

import '../modeles/contenus.dart';
import 'agenda.dart' show Agenda, ProvenanceDuTitre;
import 'api.dart';
import 'auth.dart';

/// Une tâche, contenu ouvert quand on a pu.
///
/// L'échéance est **en clair**, le contenu non. Ce n'est pas une inconséquence : le
/// serveur trie par échéance et envoie les rappels, deux choses qu'il ne saurait pas faire
/// sur une date scellée. Il sait donc *quand*, jamais *quoi*.
class Tache {
  const Tache({
    required this.id,
    required this.provenance,
    required this.titre,
    required this.faite,
    required this.creee,
    this.notes,
    this.echeance,
  });

  final String id;

  /// Les mêmes distinctions que pour l'agenda : une tâche qu'on ne sait pas ouvrir n'est
  /// ni une tâche sans titre, ni une tâche absente.
  final ProvenanceDuTitre provenance;
  final String titre;
  final String? notes;
  final DateTime? echeance;
  final bool faite;
  final DateTime creee;

  /// En retard ? Une échéance dépassée sur une tâche non faite.
  ///
  /// Calculé ici plutôt qu'à l'affichage : c'est une propriété de la tâche, pas une
  /// décoration. `maintenant` est un paramètre pour que ce soit éprouvable — sans lui,
  /// le test mesurerait l'horloge au lieu de la règle.
  bool enRetard(DateTime maintenant) {
    final quand = echeance;
    if (quand == null || faite) return false;
    return quand.isBefore(maintenant);
  }
}

/// Lire et écrire les tâches.
class Taches {
  const Taches({required this.api, required this.auth});

  final ClientAPI api;
  final Auth auth;

  Future<List<Tache>> lister({required String organisation}) async {
    final brutes = await api.obtenir<List<dynamic>>('v1/me/tasks');
    final resultat = <Tache>[];
    for (final brute in brutes.whereType<Map<String, dynamic>>()) {
      var provenance = ProvenanceDuTitre.sansTitre;
      var titre = '';
      String? notes;

      final scelle = brute['content'];
      if (scelle is String && scelle.isNotEmpty) {
        final clair = await auth.ouvrir(scelle, organisation: organisation);
        final contenu =
            clair == null ? null : ContenuDeTache.depuisJson(utf8.decode(clair));
        if (contenu == null) {
          provenance = ProvenanceDuTitre.illisible;
        } else {
          provenance = ProvenanceDuTitre.dechiffre;
          titre = contenu.title;
          notes = contenu.notes.isEmpty ? null : contenu.notes;
        }
      }

      final quand = brute['due_at'];
      resultat.add(Tache(
        id: '${brute['id']}',
        provenance: provenance,
        titre: titre,
        notes: notes,
        echeance: quand is String ? DateTime.parse(quand).toLocal() : null,
        faite: brute['completed'] == true,
        creee: DateTime.parse('${brute['created_at']}').toLocal(),
      ));
    }
    return ordonner(resultat);
  }

  /// L'ordre d'affichage : ce qui presse d'abord, ce qui est fait à la fin.
  ///
  /// Le serveur ne peut pas trier sur le titre — il ne le lit pas — mais l'échéance est en
  /// clair, et c'est elle qui compte. Les tâches **sans** échéance viennent après celles
  /// qui en ont une : les mêler par date de création ferait remonter une note vieille de
  /// six mois au-dessus d'un rendez-vous de demain.
  static List<Tache> ordonner(List<Tache> taches) {
    final copie = [...taches];
    copie.sort((a, b) {
      if (a.faite != b.faite) return a.faite ? 1 : -1;
      final x = a.echeance, y = b.echeance;
      if (x != null && y != null) return x.compareTo(y);
      if (x != null) return -1;
      if (y != null) return 1;
      return b.creee.compareTo(a.creee);
    });
    return copie;
  }

  /// Crée une tâche. Le contenu est scellé ici, l'échéance part en clair.
  Future<String> creer({
    required String titre,
    String notes = '',
    DateTime? echeance,
    required String organisation,
  }) async {
    final clair = utf8.encode(
      jsonEncode(ContenuDeTache(title: titre, notes: notes).versJson()),
    );
    final scelle = await auth.sceller(clair, organisation: organisation);
    final json = await api.envoyer<Map<String, dynamic>>('POST', 'v1/me/tasks', {
      'content': scelle,
      'due_at': echeance == null ? null : Agenda.isoPourLeServeur(echeance),
    });
    return '${json['id']}';
  }

  Future<void> marquer(String id, {required bool faite}) => api.envoyerSansReponse(
        'POST',
        'v1/me/tasks/$id/complete',
        {'completed': faite},
      );

  Future<void> supprimer(String id) =>
      api.envoyerSansReponse('DELETE', 'v1/me/tasks/$id');
}
