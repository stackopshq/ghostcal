/// Ce que les blobs scellés contiennent, une fois ouverts.
///
/// **Ces classes sont un contrat, pas une commodité.** Le serveur ne lit jamais ces
/// contenus : il stocke un blob que trois clients — le web, iOS, et bientôt celui-ci —
/// scellent et ouvrent avec la même clé. Un champ renommé d'un côté ne casse aucune
/// compilation ; il rend simplement les événements illisibles chez les autres, et l'écart
/// ne se découvre qu'en regardant deux écrans côte à côte.
///
/// La référence est `frontend/src/lib/zk.ts`. Les noms JSON y sont en anglais et le
/// restent ici : les traduire aurait été la façon la plus élégante de casser le contrat.
library;

import 'dart:convert';

/// Le contenu d'un événement — `EventContent` côté web.
class ContenuDEvenement {
  const ContenuDEvenement({
    required this.title,
    required this.description,
    required this.location,
  });

  final String title;
  final String description;
  final String location;

  /// Rend `null` plutôt que de jeter : un contenu illisible n'est pas une erreur de
  /// programme, c'est un événement scellé avec une clé qu'on n'a pas — ou écrit par une
  /// version qu'on ne connaît pas. L'agenda affiche alors un trou, il ne disparaît pas.
  static ContenuDEvenement? depuisJson(String texte) {
    try {
      final json = jsonDecode(texte);
      if (json is! Map<String, dynamic>) return null;
      final titre = json['title'];
      final description = json['description'];
      final lieu = json['location'];
      if (titre is! String || description is! String || lieu is! String) return null;
      return ContenuDEvenement(title: titre, description: description, location: lieu);
    } on FormatException {
      return null;
    }
  }

  Map<String, dynamic> versJson() => {
        'title': title,
        'description': description,
        'location': location,
      };
}

/// Le contenu d'une tâche — `TaskContent` côté web.
class ContenuDeTache {
  const ContenuDeTache({required this.title, required this.notes});

  final String title;
  final String notes;

  static ContenuDeTache? depuisJson(String texte) {
    try {
      final json = jsonDecode(texte);
      if (json is! Map<String, dynamic>) return null;
      final titre = json['title'];
      final notes = json['notes'];
      if (titre is! String || notes is! String) return null;
      return ContenuDeTache(title: titre, notes: notes);
    } on FormatException {
      return null;
    }
  }

  Map<String, dynamic> versJson() => {'title': title, 'notes': notes};
}

/// Ce que l'invité a écrit en réservant — `InviteePrivate` côté web.
class ContenuDInvite {
  const ContenuDInvite({
    required this.name,
    required this.answers,
    required this.notes,
  });

  final String name;
  final Map<String, String> answers;
  final String notes;

  static ContenuDInvite? depuisJson(String texte) {
    try {
      final json = jsonDecode(texte);
      if (json is! Map<String, dynamic>) return null;
      // **Un champ absent n'est pas un contenu corrompu**, et la nuance décidait de ce
      // que l'écran affichait.
      //
      // Ces trois clés étaient toutes exigées. Une réservation sans notes — le cas
      // ordinaire d'un invité qui n'écrit rien — rendait `null`, et l'écran Réunions
      // annonçait « nom illisible » en rouge, à côté d'une adresse parfaitement lisible.
      // Le sceau s'était pourtant ouvert sans peine : seule une clé facultative manquait.
      // Vu sur la capture App Store du 25 septembre, jamais en test.
      //
      // « Illisible » veut dire « la clé n'ouvre pas ». Le dire quand un champ est
      // simplement vide accuse la cryptographie d'une panne qui n'a pas eu lieu, et
      // inquiète sur ce qui marche.
      //
      // Le vrai échec de déchiffrement est **déjà** distingué en amont : `auth.ouvrir`
      // rend `null`, et l'appelant choisit alors « illisible ». Ici, on tient des octets
      // qu'on a su ouvrir — donc les nôtres. Être tolérant sur des champs facultatifs
      // n'ouvre aucune porte : un document qui n'est pas un objet reste refusé.
      final nom = json['name'];
      final notes = json['notes'];
      final reponses = json['answers'];
      return ContenuDInvite(
        name: nom is String ? nom : '',
        answers: reponses is Map
            ? reponses.map((cle, valeur) => MapEntry('$cle', '$valeur'))
            : const <String, String>{},
        notes: notes is String ? notes : '',
      );
    } on FormatException {
      return null;
    }
  }

  Map<String, dynamic> versJson() => {
        'name': name,
        'answers': answers,
        'notes': notes,
      };

  /// Les réponses, triées par question.
  ///
  /// Un dictionnaire n'a pas d'ordre : les afficher tels quels les ferait changer de place
  /// d'une lecture à l'autre, ce qui donne l'impression que le contenu bouge tout seul.
  List<MapEntry<String, String>> get reponsesTriees {
    final entrees = answers.entries.toList();
    entrees.sort((a, b) => a.key.compareTo(b.key));
    return entrees;
  }
}
