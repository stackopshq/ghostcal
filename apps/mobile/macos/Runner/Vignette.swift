import CoreGraphics
import FlutterMacOS
import Foundation
import ImageIO
import UniformTypeIdentifiers

/// Réduire et ré-encoder la photo de profil, parce que `image_picker` ne le fait pas ici.
///
/// ─── Ce qui manque, et comment on l'apprend ───
///
/// `ImagePicker().pickImage(maxWidth: 1024, maxHeight: 1024, imageQuality: 88)` redimensionne
/// et ré-encode sur iOS et sur Android. Sur macOS, `image_picker` n'a pas d'implémentation
/// propre : il délègue à `file_selector_macos`, c'est-à-dire à un `NSOpenPanel`. Le greffon
/// le dit dans son propre code, et c'est tout ce qui le dit :
///
///     // [ImagePickerOptions] options are not currently supported. If any
///     // of its fields are set, they will be silently ignored.
///
/// « Silently » est le mot. Rien ne lève, rien n'avertit, et le fichier remonte **tel que
/// l'utilisateur l'a choisi**. Deux conséquences, toutes deux sur le parcours normal :
///
/// · une photo d'iPhone est en HEIC. Le serveur n'accepte que PNG, JPEG, WebP et GIF —
///   `FORMATS_ACCEPTES` dans `application/avatars.py` — et refuse celle-là. L'écran montre
///   alors une erreur de téléversement pour une photo parfaitement ordinaire ;
/// · une photo de 12 Mpx pèse plusieurs méga-octets. La borne de 2 Mio tombe avant même
///   l'envoi, et le message dit « trop lourde » pour une image que l'application aurait dû
///   réduire elle-même.
///
/// ─── Pourquoi en Swift et pas en Dart ───
///
/// Parce que le HEIC. Le paquet `image` de Dart ne le décode pas, et aucun paquet Dart ne
/// le décode : le décodeur vit dans le système. ImageIO le lit comme il lit le reste, sans
/// qu'on ait à savoir ce qu'on lui donne — c'est précisément ce qu'on veut d'un fichier
/// choisi par quelqu'un d'autre.
///
/// ─── Ce qui sort ───
///
/// Du JPEG, toujours, aux mêmes mesures qu'iOS : 1024 points au plus grand côté, qualité
/// 0,88. Le serveur ré-encode de toute façon en WebP de 512 ; ce qui se joue ici n'est pas
/// la qualité finale mais le fait d'arriver — un format qu'il sait lire, sous la borne.
///
/// La vignette d'ImageIO ne reporte **que les pixels** : l'EXIF de la source, coordonnées
/// GPS comprises, ne passe pas. Le serveur l'ôterait aussi, mais une donnée de position
/// qui ne quitte pas la machine vaut mieux qu'une donnée de position effacée à l'arrivée.
enum Vignette {
  static let canal = "ch.stackops.ghostcal/vignette"

  /// Les mêmes valeurs que l'appel Dart demande à `image_picker` sur les autres
  /// plateformes. Elles vivent ici parce que c'est ici qu'elles s'appliquent.
  private static let coteMax = 1024
  private static let qualite = 0.88

  static func enregistrer(_ registrar: FlutterPluginRegistrar) {
    let canal = FlutterMethodChannel(
      name: Vignette.canal, binaryMessenger: registrar.messenger)
    canal.setMethodCallHandler { appel, repondre in
      guard appel.method == "jpeg",
        let arguments = appel.arguments as? [String: Any],
        let chemin = arguments["chemin"] as? String
      else {
        repondre(FlutterMethodNotImplemented)
        return
      }
      repondre(jpeg(chemin: chemin))
    }
  }

  /// Rend les octets JPEG, ou une erreur qui **nomme l'étape** qui a échoué.
  ///
  /// Un `nil` nu renverrait l'écran à « échec du téléversement » pour trois causes qui ne
  /// se corrigent pas de la même façon : un fichier que le bac à sable ne laisse pas lire,
  /// un fichier qui n'est pas une image, et un encodeur qui a renoncé.
  private static func jpeg(chemin: String) -> Any {
    let url = URL(fileURLWithPath: chemin)
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
      CGImageSourceGetCount(source) > 0
    else {
      return FlutterError(
        code: "illisible",
        message: "Le fichier ne s'ouvre pas comme une image : \(url.lastPathComponent)",
        details: nil)
    }

    // `…FromImageAlways` et non `…IfAbsent` : la vignette **intégrée** d'une photo
    // d'iPhone fait 160 pixels de côté, et c'est elle qu'on obtiendrait. Le drapeau impose
    // de partir de l'image entière.
    //
    // `…WithTransform` applique l'orientation EXIF. Sans lui, une photo prise à la
    // verticale arrive couchée : le serveur ré-encode les pixels, pas l'orientation, et
    // l'avatar reste de travers pour toute l'organisation.
    let options: [CFString: Any] = [
      kCGImageSourceCreateThumbnailFromImageAlways: true,
      kCGImageSourceCreateThumbnailWithTransform: true,
      kCGImageSourceThumbnailMaxPixelSize: coteMax,
    ]
    guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary)
    else {
      return FlutterError(
        code: "decodage", message: "L'image n'a pas pu être décodée.", details: nil)
    }

    let octets = NSMutableData()
    guard
      let destination = CGImageDestinationCreateWithData(
        octets, UTType.jpeg.identifier as CFString, 1, nil)
    else {
      return FlutterError(
        code: "encodage", message: "L'encodeur JPEG n'est pas disponible.", details: nil)
    }
    CGImageDestinationAddImage(
      destination, image,
      [kCGImageDestinationLossyCompressionQuality: qualite] as CFDictionary)
    guard CGImageDestinationFinalize(destination) else {
      return FlutterError(
        code: "encodage", message: "L'encodage JPEG a échoué.", details: nil)
    }
    return FlutterStandardTypedData(bytes: octets as Data)
  }
}
