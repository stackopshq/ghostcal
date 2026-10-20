import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    // Le registrar porte le messager ; `FlutterImplicitEngineBridge` ne l'expose pas
    // directement. Le nom ne sert qu'à distinguer les greffons entre eux.
    if let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "SymbolesSysteme") {
      SymbolesSysteme.enregistrer(registrar.messenger())
    }
  }
}

/// Rend un SF Symbol en PNG, pour que Flutter l'affiche.
///
/// ─── Pourquoi un pont plutôt qu'une icône de plus ───
///
/// L'écran de déverrouillage annonçait Face ID avec `Icons.face` de Material : une tête
/// ronde souriante, avec des cheveux. Relevé en rendant les six candidats Material sur
/// simulateur — `face_unlock_outlined`, `_rounded` et `_sharp` sont la **même** tête, à
/// quelques pixels près. Aucune ne ressemble au cadre carré aux coins tronqués que tout
/// utilisateur d'iPhone reconnaît.
///
/// Dessiner un sosie est la seule option exclue d'avance : les Human Interface Guidelines
/// demandent de ne pas fabriquer sa propre version de l'icône Face ID. Le symbole système
/// est en revanche fait pour cet usage — c'est déjà ce que GhostPass iOS affiche, en
/// SwiftUI, avec `Image(systemName: "faceid")`. Ce pont donne la même chose à Flutter.
///
/// ─── Ce qu'il rend, et ce qu'il ne rend pas ───
///
/// Un PNG à l'échelle de la dalle, teinté côté natif. `nil` quand le symbole n'existe pas
/// sur cette version d'iOS : l'appelant retombe alors sur son icône Material plutôt que
/// d'afficher un vide, et c'est pour cela que la méthode **ne lève pas**.
///
/// Vit dans ce fichier et non à côté : `Runner.xcodeproj` liste ses sources une par une,
/// et un fichier neuf posé sur le disque ne se compile pas tant qu'il n'y figure pas.
enum SymbolesSysteme {
  static let canal = "ch.stackops.ghostcal/symboles"

  static func enregistrer(_ messenger: FlutterBinaryMessenger) {
    let canal = FlutterMethodChannel(name: Self.canal, binaryMessenger: messenger)
    canal.setMethodCallHandler { appel, repondre in
      guard appel.method == "rendre",
            let a = appel.arguments as? [String: Any],
            let nom = a["nom"] as? String,
            let taille = a["taille"] as? Double,
            let echelle = a["echelle"] as? Double
      else {
        repondre(FlutterMethodNotImplemented)
        return
      }
      repondre(png(nom: nom,
                   taille: CGFloat(taille),
                   echelle: CGFloat(echelle),
                   couleur: (a["couleur"] as? NSNumber)?.uint32Value))
    }
  }

  private static func png(
    nom: String, taille: CGFloat, echelle: CGFloat, couleur: UInt32?
  ) -> FlutterStandardTypedData? {
    // `pointSize` plutôt qu'un redimensionnement après coup : un SF Symbol est dessiné
    // pour sa taille, et l'agrandir depuis un petit rendu le rendrait flou.
    let config = UIImage.SymbolConfiguration(pointSize: taille, weight: .regular)
    guard let symbole = UIImage(systemName: nom, withConfiguration: config) else {
      return nil
    }
    let teinte = couleur.map { valeur -> UIColor in
      UIColor(
        red: CGFloat((valeur >> 16) & 0xFF) / 255,
        green: CGFloat((valeur >> 8) & 0xFF) / 255,
        blue: CGFloat(valeur & 0xFF) / 255,
        alpha: CGFloat((valeur >> 24) & 0xFF) / 255
      )
    } ?? UIColor.label

    let format = UIGraphicsImageRendererFormat()
    format.scale = echelle
    format.opaque = false
    let rendu = UIGraphicsImageRenderer(size: symbole.size, format: format)
    let image = rendu.image { _ in
      symbole.withTintColor(teinte, renderingMode: .alwaysOriginal)
        .draw(in: CGRect(origin: .zero, size: symbole.size))
    }
    guard let donnees = image.pngData() else { return nil }
    return FlutterStandardTypedData(bytes: donnees)
  }
}
