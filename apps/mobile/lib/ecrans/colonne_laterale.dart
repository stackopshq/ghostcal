import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../l10n/generated/app_localisations.dart';
import '../outils/calendrier.dart';
import '../services/abonnements.dart';
import '../services/agenda.dart';
import '../theme.dart';

/// La colonne de gauche des fenêtres larges : les sections, les calendriers, le mois.
///
/// ─── Ce qu'elle remplace ───
///
/// Trois objets de téléphone, qui demandaient chacun un geste pour voir ce qu'ils
/// cachaient : une feuille modale pour changer de section, une autre pour filtrer les
/// calendriers, et rien du tout pour sauter à une date — il fallait cliquer les chevrons
/// autant de fois qu'il y avait de mois à franchir.
///
/// Sur un écran de bureau, ces trois choses tiennent côte à côte et restent **visibles**.
/// C'est la différence entre une application qu'on pilote et une application qu'on
/// interroge : le filtre des calendriers, caché, se oublie ; affiché, il dit en
/// permanence ce qu'on regarde et ce qu'on ne regarde pas.
///
/// ─── Ce qu'elle n'est pas ───
///
/// Pas un tiroir qu'on ouvre et qu'on referme. Elle n'apparaît qu'au-delà de
/// [Mesures.seuilBureau], où la place existe, et le téléphone garde ses feuilles. Lui
/// donner une animation d'ouverture serait réintroduire le geste qu'on vient d'enlever.
class ColonneLaterale extends StatelessWidget {
  const ColonneLaterale({
    super.key,
    required this.onglet,
    required this.surOnglet,
    required this.calendriers,
    this.surRenommage,
    this.surSuppressionDuCalendrier,
    this.surCreation,
    required this.abonnements,
    this.surAbonnement,
    this.surDesabonnement,
    required this.masques,
    required this.surMasques,
    required this.ancre,
    required this.surJour,
  });

  /// La section affichée : 0 l'agenda, puis tâches, réunions, rendez-vous, réglages.
  final int onglet;
  final ValueChanged<int> surOnglet;

  final List<Calendrier> calendriers;

  /// Renommer un calendrier qu'on possède. Nul là où personne ne peut renommer — la
  /// colonne ne dessine alors aucun crayon plutôt qu'un crayon mort.
  ///
  /// La feuille du bas porte le même geste. Les deux existent parce qu'elles ne se voient
  /// pas aux mêmes largeurs : au-dessus de 900 points la colonne remplace la feuille, et
  /// sur un iPad de treize pouces — 1032 points — c'est la colonne qu'on a sous les yeux.
  /// Un crayon qui n'existerait que dans la feuille serait introuvable là où le nom
  /// « Mon agenda » gêne le plus.
  final ValueChanged<Calendrier>? surRenommage;

  /// Supprimer un calendrier. Nul tant que l'agenda n'est pas chargé : on ne propose pas
  /// un geste définitif sur une liste qu'on n'a pas encore lue.
  ///
  /// Le nom dit « du calendrier » parce qu'une `surSuppression` vit déjà plus bas, pour
  /// les abonnements. Deux rappels de même nom dans un même fichier se confondent à la
  /// lecture, et celui qui se trompe efface la mauvaise chose.
  final ValueChanged<Calendrier>? surSuppressionDuCalendrier;

  /// Créer un calendrier. Le chemin n'existait nulle part dans l'application : la route
  /// `POST /v1/me/calendars` était là depuis toujours et seule l'interface web
  /// l'appelait. On pouvait renommer, masquer, partager — pas créer.
  final VoidCallback? surCreation;

  /// Les flux ICS, dans leur propre section. Voir [Abonnement] : ils se ressemblent assez
  /// aux calendriers pour qu'on les mélange, et assez peu pour que les confondre fasse
  /// offrir « Nouvel événement » sur un flux en lecture seule.
  final List<Abonnement> abonnements;

  /// S'abonner à un flux, et s'en désabonner. L'application n'appelait **aucune** des
  /// routes d'abonnement : on pouvait poser un flux depuis le web, ses événements
  /// s'affichaient ici — le filtre étant une liste de masqués, pas d'autorisés — mais sans
  /// son nom, sans sa couleur, sans sa case et sans moyen de l'enlever.
  final VoidCallback? surAbonnement;
  final ValueChanged<Abonnement>? surDesabonnement;

  final Set<String> masques;
  final ValueChanged<Set<String>> surMasques;

  /// Le jour autour duquel l'agenda est construit, et le moyen d'en changer.
  final DateTime ancre;
  final ValueChanged<DateTime> surJour;

  /// Assez pour « Réunions » et un nom de calendrier courant sans ellipse, pas assez
  /// pour voler de la largeur à la grille — qui en a besoin pour porter des titres.
  static const largeur = 232.0;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final l = L.of(context);
    return Container(
      width: largeur,
      decoration: BoxDecoration(
        color: gc.surface2,
        border: Border(right: BorderSide(color: gc.bordure)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // La barre de titre passe au-dessus de la colonne : sans cette réserve, la
          // première section se glisserait sous les pastilles de la fenêtre.
          const SizedBox(height: 8),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(vertical: 4),
              children: [
                _Entree(
                  icone: Icons.calendar_month_outlined,
                  libelle: l.ongletAgenda,
                  choisie: onglet == 0,
                  surChoix: () => surOnglet(0),
                ),
                for (final (indice, icone, libelle) in [
                  (1, Icons.check_box_outlined, l.ongletTaches),
                  (2, Icons.groups_outlined, l.ongletReunions),
                  (3, Icons.event_available_outlined, l.ongletRdv),
                  (4, Icons.settings_outlined, l.ongletReglages),
                ])
                  _Entree(
                    icone: icone,
                    libelle: libelle,
                    choisie: onglet == indice,
                    surChoix: () => surOnglet(indice),
                  ),
                if (calendriers.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  _Titre(l.tousLesCalendriers, surAjout: surCreation),
                  for (final c in calendriers)
                    _Calendrier(
                      surRenommage: surRenommage,
                      surSuppression: surSuppressionDuCalendrier,
                      calendrier: c,
                      visible: !masques.contains(c.id),
                      surBascule: (visible) => surMasques({
                        ...masques.where((x) => x != c.id),
                        if (!visible) c.id,
                      }),
                    ),
                ],
                // La section n'apparaît que s'il existe un flux **ou** un moyen d'en
                // ajouter : un titre « Abonnements » seul, sans ligne et sans « + »,
                // ne dirait rien à qui n'en a jamais posé.
                if (abonnements.isNotEmpty || surAbonnement != null) ...[
                  const SizedBox(height: 14),
                  _Titre(
                    l.abonnements,
                    surAjout: surAbonnement,
                    cleDAjout: const Key('colonne.nouvel-abonnement'),
                    libelleDAjout: l.nouvelAbonnement,
                  ),
                  // ─── Une section vide doit le dire ───
                  //
                  // Sans cette ligne : un intitulé, un « + » et du vide. Vu en capture
                  // sur un iPad, ça se lit comme un écran inachevé — ou comme un
                  // chargement qui n'a pas fini —, là où « TOUS LES CALENDRIERS » montre
                  // une ligne juste au-dessus. Or n'avoir aucun abonnement est l'état de
                  // la plupart des comptes, et il est parfaitement normal.
                  if (abonnements.isEmpty)
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 2, 16, 4),
                      child: Text(
                        l.aucunAbonnement,
                        style: TextStyle(fontSize: 12, color: gc.estompe),
                      ),
                    ),
                  for (final a in abonnements)
                    _Abonnement(
                      abonnement: a,
                      visible: !masques.contains(a.id),
                      surBascule: (visible) => surMasques({
                        ...masques.where((x) => x != a.id),
                        if (!visible) a.id,
                      }),
                      surSuppression: surDesabonnement,
                    ),
                ],
              ],
            ),
          ),
          Divider(height: 1, color: gc.bordure),
          _MiniMois(ancre: ancre, surJour: surJour),
        ],
      ),
    );
  }
}

class _Titre extends StatelessWidget {
  const _Titre(this.texte, {this.surAjout, this.cleDAjout, this.libelleDAjout});

  final String texte;

  /// Le « + » de la section, quand elle en a un. Au bout de l'en-tête plutôt qu'en bas
  /// de la liste : la liste s'allonge, l'en-tête non, et un bouton qui se déplace à
  /// chaque calendrier ajouté se cherche à chaque fois.
  final VoidCallback? surAjout;

  /// La clé et l'infobulle du « + », **par section**.
  ///
  /// Elles étaient en dur — `colonne.nouveau-calendrier` et « Nouveau calendrier » —
  /// tant qu'une seule section portait un bouton. À la deuxième, ça donnait deux widgets
  /// de même clé dans le même arbre, et un « + » d'abonnement qui annonçait qu'il créait
  /// un calendrier. Trouvé par le premier témoin monté sur la nouvelle section.
  final Key? cleDAjout;
  final String? libelleDAjout;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final style = TextStyle(
      fontSize: 11,
      fontWeight: FontWeight.w600,
      letterSpacing: 0.6,
      color: gc.estompe,
    );
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 6, surAjout == null ? 16 : 6, 4),
      child: Row(
        children: [
          Expanded(child: Text(texte.toUpperCase(), style: style)),
          if (surAjout != null)
            IconButton(
              key: cleDAjout ?? const Key('colonne.nouveau-calendrier'),
              icon: const Icon(Icons.add, size: 15),
              tooltip: libelleDAjout ?? L.of(context).nouveauCalendrier,
              visualDensity: VisualDensity.compact,
              constraints: const BoxConstraints(minWidth: 26, minHeight: 26),
              padding: EdgeInsets.zero,
              color: gc.estompe,
              onPressed: surAjout,
            ),
        ],
      ),
    );
  }
}

/// Une section. Le fond marque la sélection plutôt qu'une coche : c'est ce que font les
/// listes-sources de macOS, et une coche se lirait comme un filtre qu'on peut cumuler.
class _Entree extends StatelessWidget {
  const _Entree({
    required this.icone,
    required this.libelle,
    required this.choisie,
    required this.surChoix,
  });

  final IconData icone;
  final String libelle;
  final bool choisie;
  final VoidCallback surChoix;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final couleur = choisie ? gc.accentTexte : gc.encre;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 1),
      child: Material(
        color: choisie ? gc.accentTexte.withValues(alpha: 0.12) : null,
        borderRadius: BorderRadius.circular(6),
        child: InkWell(
          borderRadius: BorderRadius.circular(6),
          onTap: surChoix,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 7),
            child: Row(
              children: [
                Icon(icone, size: 17, color: couleur),
                const SizedBox(width: 9),
                Expanded(
                  child: Text(
                    libelle,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 13,
                      color: couleur,
                      fontWeight: choisie ? FontWeight.w600 : FontWeight.w400,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Un calendrier et sa case. La pastille porte sa couleur, celle que la grille emploie :
/// sans elle, décocher reviendrait à faire disparaître des lignes sans savoir lesquelles.
class _Calendrier extends StatelessWidget {
  const _Calendrier({
    required this.calendrier,
    required this.visible,
    required this.surBascule,
    this.surRenommage,
    this.surSuppression,
  });

  final Calendrier calendrier;
  final bool visible;
  final ValueChanged<bool> surBascule;
  final ValueChanged<Calendrier>? surRenommage;
  final ValueChanged<Calendrier>? surSuppression;

  /// La même lecture que `EcranDAgendaState._couleurDe` : un `#RRGGBB` que le serveur
  /// donne, et l'accent du thème quand il ne donne rien d'exploitable.
  Color _couleur(Gc gc) {
    final valeur = int.tryParse(
      calendrier.couleur.replaceFirst('#', ''),
      radix: 16,
    );
    return valeur == null ? gc.accent : Color(0xFF000000 | valeur);
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    return InkWell(
      onTap: () => surBascule(!visible),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 3),
        child: Row(
          children: [
            SizedBox(
              width: 20,
              height: 20,
              child: Checkbox(
                value: visible,
                visualDensity: VisualDensity.compact,
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                // La case prend la couleur du calendrier, comme la case de Fantastical :
                // c'est le seul endroit où le nom et la couleur se voient ensemble, et
                // donc le seul qui permette de relier une ligne colorée de la grille à
                // un calendrier qu'on peut décocher.
                fillColor: WidgetStateProperty.resolveWith(
                  (etats) => etats.contains(WidgetState.selected)
                      ? _couleur(gc)
                      : Colors.transparent,
                ),
                side: BorderSide(color: _couleur(gc), width: 1.5),
                onChanged: (v) => surBascule(v ?? false),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                calendrier.nom,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 13,
                  color: visible ? gc.encre : gc.estompe,
                ),
              ),
            ),
            // Seulement sur les siens : le serveur refuse de renommer le calendrier d'un
            // autre, sa clause `WHERE` portant le propriétaire. Un crayon qui finirait en
            // 404 serait une promesse qu'on ne tient pas.
            if (surRenommage != null && calendrier.aSoi)
              IconButton(
                key: Key('colonne.renommer.${calendrier.id}'),
                icon: const Icon(Icons.edit_outlined, size: 14),
                tooltip: L.of(context).renommerLeCalendrier,
                visualDensity: VisualDensity.compact,
                constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
                padding: EdgeInsets.zero,
                color: gc.estompe,
                onPressed: () => surRenommage!(calendrier),
              ),
            // Ni sur le calendrier par défaut, que le serveur refuse par un 409, ni sur
            // celui d'un autre. Un bouton qui échoue **après** la confirmation fait croire
            // qu'on a supprimé.
            if (surSuppression != null &&
                calendrier.aSoi &&
                !calendrier.parDefaut)
              IconButton(
                key: Key('colonne.supprimer.${calendrier.id}'),
                icon: const Icon(Icons.delete_outline, size: 14),
                tooltip: L.of(context).supprimerLeCalendrier,
                visualDensity: VisualDensity.compact,
                constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
                padding: EdgeInsets.zero,
                color: gc.estompe,
                onPressed: () => surSuppression!(calendrier),
              ),
          ],
        ),
      ),
    );
  }
}

/// Le mois en petit, en bas de la colonne.
///
/// Il sert à **sauter**, pas à lire : trente et un nombres de onze points ne disent pas
/// ce qu'il y a dans la journée, et ne prétendent pas le dire — aucune pastille, aucun
/// titre. Ce qu'il donne, c'est le mois entier d'un coup d'œil et n'importe quel jour en
/// un clic, là où les chevrons de l'en-tête demandent un clic par période franchie.
class _MiniMois extends StatelessWidget {
  const _MiniMois({required this.ancre, required this.surJour});

  final DateTime ancre;
  final ValueChanged<DateTime> surJour;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final locale = Localizations.localeOf(context).toLanguageTag();
    final premierJour = MaterialLocalizations.of(context).firstDayOfWeekIndex;
    final jours = joursDeLaGrilleDuMois(ancre, premierJour);
    final aujourdhui = minuit(DateTime.now());
    final choisi = minuit(ancre);

    return Padding(
      padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
      child: Column(
        children: [
          Row(
            children: [
              _Chevron(
                icone: Icons.chevron_left,
                surClic: () => surJour(plusMois(ancre, -1)),
              ),
              Expanded(
                child: Text(
                  DateFormat.yMMMM(locale).format(ancre),
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: gc.encre,
                  ),
                ),
              ),
              _Chevron(
                icone: Icons.chevron_right,
                surClic: () => surJour(plusMois(ancre, 1)),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              for (final jour in jours.take(7))
                Expanded(
                  child: Text(
                    DateFormat.E(locale).format(jour).characters.first,
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 10, color: gc.estompe),
                  ),
                ),
            ],
          ),
          for (var rang = 0; rang < 6; rang++)
            Row(
              children: [
                for (final jour in jours.skip(rang * 7).take(7))
                  Expanded(
                    child: _JourDuMini(
                      jour: jour,
                      duMois: jour.month == ancre.month,
                      aujourdhui: minuit(jour) == aujourdhui,
                      choisi: minuit(jour) == choisi,
                      surClic: () => surJour(jour),
                    ),
                  ),
              ],
            ),
        ],
      ),
    );
  }
}

class _Chevron extends StatelessWidget {
  const _Chevron({required this.icone, required this.surClic});

  final IconData icone;
  final VoidCallback surClic;

  @override
  Widget build(BuildContext context) => InkWell(
    onTap: surClic,
    borderRadius: BorderRadius.circular(4),
    child: Padding(
      padding: const EdgeInsets.all(2),
      child: Icon(icone, size: 16, color: Gc.of(context).estompe),
    ),
  );
}

class _JourDuMini extends StatelessWidget {
  const _JourDuMini({
    required this.jour,
    required this.duMois,
    required this.aujourdhui,
    required this.choisi,
    required this.surClic,
  });

  final DateTime jour;
  final bool duMois;
  final bool aujourdhui;
  final bool choisi;
  final VoidCallback surClic;

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    // Aujourd'hui l'emporte sur la sélection : c'est le repère, et le perdre de vue en
    // naviguant ferait perdre le nord dans un mois qu'on ne reconnaît pas.
    final fond = aujourdhui
        ? gc.accentTexte
        : (choisi ? gc.accentTexte.withValues(alpha: 0.16) : null);
    final encre = aujourdhui
        ? Gc.surAccent
        : (duMois ? gc.encre : gc.estompe.withValues(alpha: 0.6));
    return InkWell(
      onTap: surClic,
      customBorder: const CircleBorder(),
      child: Container(
        height: 22,
        alignment: Alignment.center,
        child: Container(
          width: 20,
          height: 20,
          alignment: Alignment.center,
          decoration: BoxDecoration(color: fond, shape: BoxShape.circle),
          child: Text(
            '${jour.day}',
            style: TextStyle(
              fontSize: 11,
              color: encre,
              fontWeight: aujourdhui || choisi
                  ? FontWeight.w600
                  : FontWeight.w400,
            ),
          ),
        ),
      ),
    );
  }
}

/// Un abonnement, sa case et sa corbeille.
///
/// La même rangée qu'un calendrier à deux choses près, et les deux disent ce qu'un
/// abonnement a de différent :
///
/// - **une corbeille et pas de crayon.** On ne renomme pas un flux : son nom est celui
///   qu'on lui a donné en s'y abonnant, et l'API ne le modifie pas. Se désabonner est en
///   revanche le seul geste que l'application ne savait pas faire.
/// - **un avertissement quand le flux ne répond plus.** Ce qui s'affiche vient alors du
///   dernier rapatriement réussi. Le taire laisserait croire à un agenda à jour, et c'est
///   le pire des deux états possibles : un agenda faux qu'on croit juste.
class _Abonnement extends StatelessWidget {
  const _Abonnement({
    required this.abonnement,
    required this.visible,
    required this.surBascule,
    this.surSuppression,
  });

  final Abonnement abonnement;
  final bool visible;
  final ValueChanged<bool> surBascule;
  final ValueChanged<Abonnement>? surSuppression;

  Color _couleur(Gc gc) {
    final valeur = int.tryParse(
      abonnement.couleur.replaceFirst('#', ''),
      radix: 16,
    );
    return valeur == null ? gc.accent : Color(0xFF000000 | valeur);
  }

  @override
  Widget build(BuildContext context) {
    final gc = Gc.of(context);
    final l = L.of(context);
    return InkWell(
      onTap: () => surBascule(!visible),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 3),
        child: Row(
          children: [
            SizedBox(
              width: 20,
              height: 20,
              child: Checkbox(
                value: visible,
                visualDensity: VisualDensity.compact,
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                fillColor: WidgetStateProperty.resolveWith(
                  (etats) => etats.contains(WidgetState.selected)
                      ? _couleur(gc)
                      : Colors.transparent,
                ),
                side: BorderSide(color: _couleur(gc), width: 1.5),
                onChanged: (v) => surBascule(v ?? false),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    abonnement.nom,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 13,
                      color: visible ? gc.encre : gc.estompe,
                    ),
                  ),
                  if (abonnement.enPanne)
                    Text(
                      l.abonnementEnPanne,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 11, color: gc.danger),
                    ),
                ],
              ),
            ),
            if (surSuppression != null)
              IconButton(
                key: Key('colonne.desabonner.${abonnement.id}'),
                icon: const Icon(Icons.delete_outline, size: 18),
                tooltip: l.supprimerLAbonnement,
                visualDensity: VisualDensity.compact,
                onPressed: () => surSuppression!(abonnement),
              ),
          ],
        ),
      ),
    );
  }
}
