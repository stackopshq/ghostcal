import 'package:flutter/material.dart';

import '../l10n/generated/app_localisations.dart';

/// Ce qu'il faut pour poser un abonnement : un nom, et l'adresse du flux.
typedef FluxDemande = ({String nom, String url});

/// Demande un flux ICS, et ne rend que ce qui mérite d'être envoyé.
///
/// Rend `null` si la boîte est annulée ou si l'un des deux champs est vide.
///
/// ─── Ce qui n'est pas vérifié ici, et pourquoi ───
///
/// L'URL n'est ni validée ni réécrite. Apple, Google et Outlook donnent des liens
/// `webcal://` — un schéma qui n'a jamais existé ailleurs que dans les clients de
/// bureau et qui désigne la même ressource en HTTPS —, et un copier-coller depuis une
/// feuille de partage ramène régulièrement une espace finale, invisible à l'œil. Le
/// serveur traite déjà les deux cas, et il va **lire** le flux avant de l'enregistrer :
/// une adresse injoignable revient en 422, à la création, et non en silence dans un
/// travail de fond.
///
/// Refaire ce travail ici donnerait deux règles à tenir d'accord, et c'est la copie qui
/// se tromperait. Le champ accepte donc ce qu'on y colle, et l'erreur du serveur est
/// montrée telle quelle par l'appelant.
///
/// ─── Pourquoi une fonction à part ───
///
/// La même raison que `renommer_un_calendrier.dart` : l'accueil réclame une session
/// ouverte, donc un serveur et le cœur Rust. Un témoin monté sur lui éprouverait surtout
/// le harnais. Ici, la règle s'éprouve seule.
Future<FluxDemande?> demanderUnAbonnement(BuildContext context) async {
  final choisi = await showDialog<FluxDemande>(
    context: context,
    builder: (context) => const _BoiteDAbonnement(),
  );
  if (choisi == null) return null;
  final nom = choisi.nom.trim();
  final url = choisi.url.trim();
  if (nom.isEmpty || url.isEmpty) return null;
  return (nom: nom, url: url);
}

/// La boîte, qui **possède** ses deux contrôleurs.
///
/// `StatefulWidget` et non deux contrôleurs créés par la fonction ci-dessus : voir
/// `renommer_un_calendrier.dart`, où la question est posée en entier. `showDialog` rend
/// la main pendant que l'arbre de la boîte se démonte encore, et libérer à cet instant
/// retire un contrôleur sous un widget vivant — une assertion du cœur de Flutter qui ne
/// nomme ni le champ ni le contrôleur.
class _BoiteDAbonnement extends StatefulWidget {
  const _BoiteDAbonnement();

  @override
  State<_BoiteDAbonnement> createState() => _EtatBoiteDAbonnement();
}

class _EtatBoiteDAbonnement extends State<_BoiteDAbonnement> {
  final _nom = TextEditingController();
  final _url = TextEditingController();

  @override
  void dispose() {
    _nom.dispose();
    _url.dispose();
    super.dispose();
  }

  void _valider() =>
      Navigator.of(context).pop((nom: _nom.text, url: _url.text));

  @override
  Widget build(BuildContext context) {
    final l = L.of(context);
    return AlertDialog(
      title: Text(l.nouvelAbonnement),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            key: const Key('abonnement.nom'),
            controller: _nom,
            autofocus: true,
            textInputAction: TextInputAction.next,
            decoration: InputDecoration(labelText: l.nom),
          ),
          const SizedBox(height: 12),
          TextField(
            key: const Key('abonnement.url'),
            controller: _url,
            keyboardType: TextInputType.url,
            autocorrect: false,
            // L'adresse d'un flux ne commence pas par une majuscule, et une correction
            // automatique sur une URL collée la casserait sans le dire.
            textCapitalization: TextCapitalization.none,
            onSubmitted: (_) => _valider(),
            decoration: InputDecoration(
              labelText: l.adresseDuFlux,
              hintText: 'https://…/calendrier.ics',
            ),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(l.annuler),
        ),
        TextButton(
          key: const Key('abonnement.ajouter'),
          onPressed: _valider,
          child: Text(l.creer),
        ),
      ],
    );
  }
}
