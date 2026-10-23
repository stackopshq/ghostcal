import 'package:flutter/material.dart';

import '../l10n/generated/app_localisations.dart';

/// Demande un nouveau nom de calendrier, et ne rend que ce qui mérite d'être envoyé.
///
/// Rend `null` dans les trois cas où il n'y a rien à faire : la boîte a été annulée, le
/// champ est vide, ou le nom revient identique à celui qu'on avait. Le dernier cas est le
/// moins évident et le plus fréquent — on ouvre la boîte, on regarde, on valide. Un
/// `PATCH` qui repose la même valeur réussirait, ne prouverait rien, et coûterait un
/// aller-retour sur un réseau mobile.
///
/// Cette fonction vit à part de l'écran d'accueil pour une raison mesurable : l'accueil
/// réclame une session ouverte, donc un serveur et le cœur Rust. Un témoin monté sur lui
/// éprouverait surtout le harnais. Ici, la règle s'éprouve seule.
Future<String?> demanderUnNouveauNom(
  BuildContext context, {
  required String nomActuel,
}) async {
  final choisi = await showDialog<String>(
    context: context,
    builder: (context) => _BoiteDeRenommage(nomActuel: nomActuel),
  );
  final propre = choisi?.trim() ?? '';
  if (propre.isEmpty || propre == nomActuel.trim()) return null;
  return propre;
}

/// Demande le nom d'un calendrier à créer.
///
/// La même boîte que le renommage, avec un autre titre : les deux posent la même
/// question, et deux boîtes jumelles divergeraient à la première correction faite d'un
/// seul côté — c'est déjà la raison pour laquelle création et modification d'un
/// événement partagent un écran.
///
/// Rend `null` si la boîte est annulée ou si le champ est vide. Pas de comparaison à
/// l'existant ici : il n'y a rien à comparer, et deux calendriers peuvent légitimement
/// porter le même nom — « Perso » sur deux comptes, par exemple.
Future<String?> demanderUnNomDeCalendrier(BuildContext context) async {
  final choisi = await showDialog<String>(
    context: context,
    builder: (context) =>
        const _BoiteDeRenommage(nomActuel: '', creation: true),
  );
  final propre = choisi?.trim() ?? '';
  return propre.isEmpty ? null : propre;
}

/// La boîte, qui **possède** son contrôleur de saisie.
///
/// Première version : le contrôleur était créé par la fonction ci-dessus et libéré dès
/// que `showDialog` rendait la main. Les témoins ont échoué sur
/// `'_dependents.isEmpty': is not true` — une assertion du cœur de Flutter, qui ne nomme
/// ni le contrôleur ni le champ et invite à ouvrir un bogue chez eux.
///
/// La cause est l'ordre : `showDialog` rend la main dès que la route est dépilée, alors
/// que l'arbre de la boîte **se démonte encore**, champ et focus compris. Libérer à cet
/// instant retire le contrôleur sous un widget vivant. En production le symptôme aurait
/// été intermittent, parce qu'il dépend de la durée de l'animation de fermeture.
///
/// Un `StatefulWidget` règle la question en la posant au bon endroit : le contrôleur naît
/// et meurt avec le widget qui s'en sert.
class _BoiteDeRenommage extends StatefulWidget {
  const _BoiteDeRenommage({required this.nomActuel, this.creation = false});

  final String nomActuel;

  /// Change le titre et le bouton, rien d'autre : le champ, la validation par Entrée et
  /// le cycle de vie du contrôleur sont les mêmes.
  final bool creation;

  @override
  State<_BoiteDeRenommage> createState() => _EtatBoiteDeRenommage();
}

class _EtatBoiteDeRenommage extends State<_BoiteDeRenommage> {
  late final TextEditingController _saisie = TextEditingController(
    text: widget.nomActuel,
  );

  @override
  void dispose() {
    _saisie.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l = L.of(context);
    return AlertDialog(
      title: Text(
        widget.creation ? l.nouveauCalendrier : l.renommerLeCalendrier,
      ),
      content: TextField(
        key: const Key('calendriers.renommer.champ'),
        controller: _saisie,
        autofocus: true,
        textCapitalization: TextCapitalization.sentences,
        decoration: InputDecoration(labelText: l.nom),
        // Entrée valide, comme la touche « OK » du clavier logiciel. Obliger à viser un
        // bouton après avoir tapé un mot est un geste de trop sur un téléphone.
        onSubmitted: (valeur) => Navigator.of(context).pop(valeur),
      ),
      actions: [
        TextButton(
          key: const Key('calendriers.renommer.annuler'),
          onPressed: () => Navigator.of(context).pop(),
          child: Text(l.annuler),
        ),
        FilledButton(
          key: const Key('calendriers.renommer.valider'),
          onPressed: () => Navigator.of(context).pop(_saisie.text),
          child: Text(widget.creation ? l.creer : l.enregistrer),
        ),
      ],
    );
  }
}
