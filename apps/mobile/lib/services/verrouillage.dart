import 'package:flutter/foundation.dart';

import 'trousseau.dart';
import '../l10n/generated/app_localisations.dart';

/// Au bout de combien de temps le coffre se referme quand l'application passe en arrière-plan.
///
/// Porté de `Preferences.Verrouillage` de GhostPass iOS, valeurs comprises. Un coffre qui
/// reste ouvert pendant que le téléphone circule n'est plus un coffre — mais le refermer à
/// chaque aller-retour vers le navigateur fait renoncer à s'en servir. D'où un délai
/// réglable, **immédiat par défaut** : c'est le choix sûr, et celui qui se desserre
/// sciemment.
enum DelaiDeVerrouillage {
  immediat(null),
  uneMinute(Duration(minutes: 1)),
  cinqMinutes(Duration(minutes: 5)),
  quinzeMinutes(Duration(minutes: 15));

  const DelaiDeVerrouillage(this.delai);

  /// Le libellé, dans la langue de l'appareil.
  ///
  /// C'était une constante française portée par l'énumération. Une énumération est une
  /// donnée : le texte qui la nomme dépend de la langue et n'a rien à y faire en dur.
  ///
  /// La correspondance reste ici, collée aux valeurs, parce qu'un `switch` sur une
  /// énumération est **exhaustif** : ajouter un délai sans lui donner de libellé ne
  /// compile pas. Une table posée ailleurs laisserait passer l'oubli, et l'écran
  /// afficherait un vide là où un délai devrait se lire.
  String libelle(L l) => switch (this) {
        DelaiDeVerrouillage.immediat => l.verrouillageImmediat,
        DelaiDeVerrouillage.uneMinute => l.verrouillage1Minute,
        DelaiDeVerrouillage.cinqMinutes => l.verrouillage5Minutes,
        DelaiDeVerrouillage.quinzeMinutes => l.verrouillage15Minutes,
      };

  /// Nul veut dire « tout de suite », et non « jamais ». La distinction compte : un nul lu
  /// comme « pas de verrouillage » ouvrirait le coffre en grand.
  final Duration? delai;
}

/// Le réglage, retenu entre deux lancements.
class Verrouillage extends ChangeNotifier {
  static const _cle = 'ghostcal.verrouillage';

  DelaiDeVerrouillage _choix = DelaiDeVerrouillage.immediat;
  DelaiDeVerrouillage get choix => _choix;

  /// La règle, **sans état** : elle ne dépend que du choix et de deux instants.
  ///
  /// Sortie de l'objet pour être éprouvable sans trousseau — un test qui doit amorcer un
  /// magasin sécurisé pour vérifier une soustraction de dates mesure surtout le magasin.
  static bool refermeApres(
    DelaiDeVerrouillage choix, {
    required DateTime depuis,
    required DateTime maintenant,
  }) {
    final delai = choix.delai;
    if (delai == null) return true;
    // Borne incluse : à cinq minutes pile, on referme. « Strictement après » laisserait le
    // coffre ouvert une seconde de plus pour rien.
    return maintenant.difference(depuis) >= delai;
  }

  /// Le cadenas n'a de sens que si le verrouillage automatique attend.
  ///
  /// Avec le réglage par défaut — immédiat — quitter l'application referme déjà le coffre :
  /// le bouton occuperait la meilleure place de la barre pour un geste que le système fait
  /// tout seul. Dès qu'un délai est réglé, il redevient le seul moyen de verrouiller
  /// sur-le-champ.
  bool get cadenasVisible => cadenasVisiblePour(_choix);

  static bool cadenasVisiblePour(DelaiDeVerrouillage choix) =>
      choix != DelaiDeVerrouillage.immediat;

  Future<void> amorcer() async {
    final brut = await Trousseau.lire(_cle);
    _choix = DelaiDeVerrouillage.values.firstWhere(
      (v) => v.name == brut,
      // Une valeur inconnue — écrite par une version plus récente — retombe sur le choix
      // **sûr**, jamais sur le plus permissif.
      orElse: () => DelaiDeVerrouillage.immediat,
    );
    notifyListeners();
  }

  Future<void> choisir(DelaiDeVerrouillage valeur) async {
    _choix = valeur;
    notifyListeners();
    await Trousseau.poser(valeur.name, _cle);
  }

  /// Faut-il refermer, après être resté en arrière-plan depuis [depuis] ?
  ///
  /// L'instant est un paramètre pour que ce soit éprouvable : sans lui, le test mesurerait
  /// l'horloge au lieu de la règle.
  bool doitVerrouiller({required DateTime depuis, required DateTime maintenant}) =>
      refermeApres(_choix, depuis: depuis, maintenant: maintenant);
}
