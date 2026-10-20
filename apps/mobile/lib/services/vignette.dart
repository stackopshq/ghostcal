import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Réduire et ré-encoder une image choisie, là où le sélecteur ne le fait pas.
///
/// `ImagePicker` honore `maxWidth`, `maxHeight` et `imageQuality` sur iOS et sur Android.
/// Sur macOS il les **ignore en silence** — c'est écrit dans `image_picker_macos`, qui
/// n'est qu'un `NSOpenPanel` déguisé — et le fichier remonte tel quel : une photo d'iPhone
/// en HEIC, que le serveur refuse, et de plusieurs méga-octets, que la borne de 2 Mio
/// refuse avant lui.
///
/// Le travail se fait donc du côté natif, parce que le décodeur HEIC vit dans le système
/// et nulle part en Dart. Voir `macos/Runner/Vignette.swift` pour le détail et les choix.
///
/// Cette classe n'existe que pour macOS, et le dit : ailleurs, [reduire] rend `null` et
/// l'appelant garde le chemin qu'il avait — refaire ici ce qu'`image_picker` fait déjà
/// ferait deux ré-encodages là où un seul suffit.
class Vignette {
  const Vignette({MethodChannel? canal, this.plateforme})
      : _canal = canal ?? const MethodChannel(_nom);

  static const _nom = 'ch.stackops.ghostcal/vignette';

  final MethodChannel _canal;

  /// La plateforme, imposée par un témoin. `null` suit l'appareil.
  ///
  /// Publique parce qu'un champ privé ne se pose pas depuis un constructeur :
  /// `this._plateforme` nommerait le paramètre `_plateforme`, qu'aucun appelant ne peut
  /// écrire. La couture est la même que celle de `Biometrie`.
  final TargetPlatform? plateforme;

  bool get _surMacos =>
      (plateforme ?? defaultTargetPlatform) == TargetPlatform.macOS;

  /// Les octets JPEG de l'image en [chemin], ou `null` hors macOS.
  ///
  /// **Ne rattrape pas.** Une `PlatformException` remonte avec le code de l'étape qui a
  /// échoué — `illisible`, `decodage`, `encodage` —, et l'écran l'affiche comme il
  /// affiche les autres. L'avaler ici rendrait `null`, c'est-à-dire « pas sur macOS »,
  /// et l'appelant téléverserait le HEIC qu'on cherchait justement à ne pas envoyer.
  Future<Uint8List?> reduire(String chemin) async {
    if (!_surMacos) return null;
    return _canal.invokeMethod<Uint8List>('jpeg', {'chemin': chemin});
  }
}
