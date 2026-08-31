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
      final nom = json['name'];
      final notes = json['notes'];
      final reponses = json['answers'];
      if (nom is! String || notes is! String || reponses is! Map) return null;
      return ContenuDInvite(
        name: nom,
        answers: reponses.map((cle, valeur) => MapEntry('$cle', '$valeur')),
        notes: notes,
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
