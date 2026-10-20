
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Un SF Symbol d'iOS, avec repli Material partout ailleurs.
///
/// ─── Pourquoi ce détour pour une icône ───
///
/// L'écran de déverrouillage annonçait Face ID avec `Icons.face` : une tête ronde
/// souriante, avec des cheveux. Les six candidats Material ont été **rendus sur
/// simulateur** avant de conclure — `face_unlock_outlined`, `_rounded` et `_sharp` sont
/// la même tête à quelques pixels près. Material n'a rien qui ressemble au cadre carré
/// aux coins tronqués de Face ID.
///
/// Dessiner un sosie est exclu : les Human Interface Guidelines demandent de ne pas
/// fabriquer sa propre version de cette icône. Le symbole système, lui, est fait pour
/// ça — et c'est déjà ce que GhostPass iOS affiche en SwiftUI.
///
/// ─── Le repli n'est pas décoratif ───
///
/// Trois cas y mènent, et aucun ne doit laisser un trou à l'écran : Android, où ces
/// symboles n'existent pas ; une version d'iOS qui ne connaît pas le nom demandé ; et la
/// première image, le temps que le canal réponde. Dans les trois, [materiel] s'affiche.
class SymboleSysteme extends StatefulWidget {
  const SymboleSysteme({
    super.key,
    required this.nom,
    required this.materiel,
    this.taille = 24,
    this.couleur,
  });

  /// Le nom du symbole Apple, par exemple `faceid`.
  final String nom;

  /// Ce qu'on montre là où le symbole n'existe pas.
  final IconData materiel;

  final double taille;
  final Color? couleur;

  static const _canal = MethodChannel('ch.stackops.ghostcal/symboles');

  /// Les rendus déjà obtenus, pour ne pas retraverser le canal à chaque image.
  static final _cache = <String, Uint8List?>{};

  static bool get _surIOS =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS;

  /// Vide le cache. Pour les témoins, qui changent de faux canal entre deux cas.
  @visibleForTesting
  static void oublierLeCache() => _cache.clear();

  @override
  State<SymboleSysteme> createState() => _EtatDuSymbole();
}

class _EtatDuSymbole extends State<SymboleSysteme> {
  Uint8List? _png;
  String? _cle;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _charger();
  }

  @override
  void didUpdateWidget(SymboleSysteme ancien) {
    super.didUpdateWidget(ancien);
    _charger();
  }

  Color _teinte() =>
      widget.couleur ?? IconTheme.of(context).color ?? Theme.of(context).iconTheme.color ?? Colors.black;

  Future<void> _charger() async {
    if (!SymboleSysteme._surIOS) return;
    final echelle = MediaQuery.maybeDevicePixelRatioOf(context) ?? 1;
    final couleur = _teinte();
    // La clé porte tout ce qui change le rendu : un même symbole en deux tailles ou deux
    // couleurs sont deux images, et les confondre afficherait la précédente.
    final cle = '${widget.nom}|${widget.taille}|$echelle|${couleur.toARGB32()}';
    if (cle == _cle) return;
    _cle = cle;

    if (SymboleSysteme._cache.containsKey(cle)) {
      setState(() => _png = SymboleSysteme._cache[cle]);
      return;
    }
    Uint8List? png;
    try {
      png = await SymboleSysteme._canal.invokeMethod<Uint8List>('rendre', {
        'nom': widget.nom,
        'taille': widget.taille,
        'echelle': echelle,
        'couleur': couleur.toARGB32(),
      });
    } on PlatformException {
      png = null; // Le repli Material reste à l'écran.
    } on MissingPluginException {
      png = null;
    }
    SymboleSysteme._cache[cle] = png;
    if (mounted && cle == _cle) setState(() => _png = png);
  }

  @override
  Widget build(BuildContext context) {
    final png = _png;
    if (png == null) {
      return Icon(widget.materiel, size: widget.taille, color: widget.couleur);
    }
    return Image.memory(
      png,
      height: widget.taille,
      // Le symbole est déjà teinté côté natif : le refaire ici l'assombrirait.
      filterQuality: FilterQuality.medium,
      gaplessPlayback: true,
    );
  }
}
