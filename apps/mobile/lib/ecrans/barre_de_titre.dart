import 'package:flutter/material.dart';

import '../l10n/generated/app_localisations.dart';
import '../services/vue_agenda.dart';
import '../theme.dart';

/// La barre d'outils du bureau, logée **dans** la barre de titre de la fenêtre.
///
/// ─── Pourquoi elle existe ───
///
/// Sans elle, une fenêtre large porte une barre de titre vide au-dessus des commandes
/// de l'application : deux bandeaux empilés dont le premier ne sert à rien. Et les
/// commandes, elles, restaient en bas dans une pilule flottante — un objet fait pour
/// un pouce, posé devant une souris.
///
/// ─── Pourquoi elle est un widget public, et pas une méthode de l'accueil ───
///
/// Elle l'a été, et le défaut qu'elle porte est passé **deux fois** : la barre se
/// dessinait par-dessus l'heure de l'iPad, une première fois parce que la marge haute
/// était retirée à tort, une seconde parce qu'elle était préservée sans que personne ne
/// la lise. Les deux fois, aucun témoin n'a mordu.
///
/// La raison est structurelle : `EcranDAccueil` **ne se monte pas en test**. Il lui faut
/// une session ouverte, et c'est déjà pourquoi `menu_macos_test.dart` et `fond_test.dart`
/// lisent le source au lieu de monter quoi que ce soit. Tant que la barre vivait dans une
/// méthode privée de cet écran, elle était hors d'atteinte, et les seuls témoins
/// possibles étaient des fonctions pures — qui restent vertes quand le défaut est de ne
/// **pas** les appeler. C'était exactement le cas ici.
///
/// Sortie ici, elle se monte seule sous une `MediaQuery` choisie, et sa hauteur rendue
/// se mesure. Voir `test/barre_de_titre_test.dart`.
class BarreDeTitreDeBureau extends StatelessWidget
    implements PreferredSizeWidget {
  const BarreDeTitreDeBureau({
    super.key,
    required this.encoche,
    required this.vue,
    required this.surVue,
    required this.surRecherche,
    required this.peutCreer,
    required this.surNouveau,
  });

  /// Hauteur de la barre elle-même, encoche non comprise. Les pastilles de la fenêtre
  /// sont centrées verticalement dedans, comme dans Fantastical et les Réglages Système.
  ///
  /// C'est aussi la marge que `_SousLaBarreDeTitre` réserve dans `main.dart` : les deux
  /// nombres doivent être le même, sans quoi un écran poussé commence au-dessus ou en
  /// dessous de la barre.
  static const hauteur = 52.0;

  /// La place des trois pastilles de la fenêtre macOS.
  ///
  /// `MainFlutterWindow` rend la barre de titre transparente et fait passer la vue
  /// Flutter dessous. Les pastilles se retrouvent donc **sur cette ligne**, et le bord
  /// gauche leur appartient : y poser un bouton le rendrait inatteignable, sans que rien
  /// ne le signale.
  ///
  /// Mesuré le 2026-10-22 par `System Events`, barre de titre unifiée comprise : trois
  /// pastilles de 16×16 à x = 18, 41 et 64, donc occupées jusqu'à 80. La marge vaut 96
  /// et non 80 — seize points de respiration, sans quoi le premier bouton les touche.
  ///
  /// Sur iPad ces 96 points ne servent à rien, mais ils ne gênent pas : les deux icônes
  /// de droite les compensent, et le segmenté reste centré à trois points près —
  /// vérifié sur la capture avant d'y toucher.
  static const margeDesPastilles = 96.0;

  /// Ce que la barre doit ajouter à sa hauteur pour ne pas se poser sur la barre d'état.
  ///
  /// ─── Pourquoi ce n'est pas automatique ───
  ///
  /// Cette barre est un `PreferredSizeWidget` ordinaire, pas un `AppBar`. **Seul `AppBar`
  /// lit `MediaQuery.padding.top` et s'agrandit d'autant** ; tout le reste se pose à
  /// y = 0 quoi qu'il arrive.
  ///
  /// Sur macOS c'est voulu : l'application dessine dans la barre de titre, et la marge a
  /// justement été retirée en amont par l'accueil. Sur un **iPad** — large, donc
  /// « bureau », mais avec une vraie barre d'état — la barre d'outils se dessinait par
  /// dessus l'heure, le wifi et la batterie. Mesuré sur `captures-ipad/01-agenda.png` :
  /// le trait du bas tombait à 104 pixels physiques, soit exactement les 52 points de la
  /// barre, donc elle commençait bien à zéro.
  ///
  /// La plateforme est **passée** et non lue ici : l'accueil s'en sert aussi pour décider
  /// du `MediaQuery.removePadding`, et les deux décisions doivent venir du même nombre.
  /// Lire `defaultTargetPlatform` d'un côté et `Theme.of(context).platform` de l'autre
  /// les laisserait diverger dès qu'un thème nomme sa plateforme.
  static double encocheSelon(BuildContext context, TargetPlatform plateforme) =>
      Mesures.dansLaBarreDeTitre(bureau: true, plateforme: plateforme)
      ? 0.0
      : MediaQuery.paddingOf(context).top;

  /// Ce qu'[encocheSelon] a rendu. La hauteur rendue **et** [preferredSize] en
  /// descendent, pour qu'une des deux ne puisse pas l'oublier.
  final double encoche;

  final VueDAgenda vue;
  final ValueChanged<VueDAgenda> surVue;
  final VoidCallback surRecherche;

  /// Sans calendrier inscriptible, offrir de créer mènerait à un formulaire qu'on ne peut
  /// pas enregistrer. Même règle que la barre du bas.
  final bool peutCreer;
  final VoidCallback surNouveau;

  @override
  Size get preferredSize => Size.fromHeight(hauteur + encoche);

  @override
  Widget build(BuildContext context) {
    final l = L.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(color: Theme.of(context).dividerColor),
        ),
      ),
      child: SizedBox(
        height: hauteur + encoche,
        child: Padding(
          padding: EdgeInsets.only(
            top: encoche,
            left: margeDesPastilles,
            right: 8,
          ),
          child: Row(
            children: [
              // Ni hamburger ni filtre : la colonne porte les sections et les
              // calendriers, en permanence. Les garder ici donnerait deux chemins
              // vers la même chose, dont un caché — ce qu'on vient d'enlever.
              Expanded(child: Center(child: _vues(context, l))),
              IconButton(
                key: const Key('accueil.recherche'),
                tooltip: l.rechercher,
                icon: const Icon(Icons.search),
                onPressed: surRecherche,
              ),
              if (peutCreer)
                IconButton(
                  key: const Key('accueil.nouveau'),
                  tooltip: l.nouvelEvenement,
                  icon: const Icon(Icons.add),
                  onPressed: surNouveau,
                ),
            ],
          ),
        ),
      ),
    );
  }

  /// Les quatre vues, en segmenté permanent plutôt que cachées dans une feuille.
  Widget _vues(BuildContext context, L l) => SegmentedButton<VueDAgenda>(
    key: const Key('bureau.vues'),
    showSelectedIcon: false,
    style: const ButtonStyle(
      visualDensity: VisualDensity.compact,
      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
    ),
    segments: [
      for (final v in VueDAgenda.values)
        ButtonSegment<VueDAgenda>(value: v, label: Text(v.libelle(l))),
    ],
    selected: {vue},
    onSelectionChanged: (choix) => surVue(choix.first),
  );
}
