import FlutterMacOS
import Foundation
import ServiceManagement

/// Inscrire l'application aux ouvertures de session, et rien d'autre.
///
/// ─── Pourquoi il reste si peu à faire ici ───
///
/// Les bannières ne passent pas par ce fichier : `flutter_local_notifications` les
/// programme sur macOS comme sur Android, et le centre de notifications les présente à
/// l'heure dite, même application fermée. Le texte, le délai et ce qui mérite un rappel
/// vivent donc en Dart, dans `services/rappels.dart`, où ils sont éprouvés sans machine —
/// et c'est important pour le **texte**, la seule partie de cette fonction qui puisse
/// fuir une donnée. Composé ici, il serait hors de portée de tout témoin.
///
/// Ce qui n'a pas d'équivalent, c'est le rafraîchissement. `workmanager` passe ici par
/// `NSBackgroundActivityScheduler`, qui « only fires while the app process is alive and
/// the Mac is awake » — sa propre documentation. Android réveille un téléphone fermé ;
/// macOS ne réveille rien. Rendre à l'application l'occasion de tourner est donc le seul
/// moyen, et c'est tout ce que fait ce fichier.
enum OuvertureDeSession {
  static let canal = "ch.stackops.ghostcal/rappels"

  static func enregistrer(_ registrar: FlutterPluginRegistrar) {
    let canal = FlutterMethodChannel(
      name: OuvertureDeSession.canal, binaryMessenger: registrar.messenger)
    canal.setMethodCallHandler { appel, repondre in
      switch appel.method {
      case "lancerALOuvertureDeSession":
        let arguments = appel.arguments as? [String: Any] ?? [:]
        repondre(inscrire(arguments["valeur"] as? Bool ?? false))
      case "lanceALOuvertureDeSession":
        repondre(inscrit())
      default:
        repondre(FlutterMethodNotImplemented)
      }
    }
  }

  /// Inscrit ou retire, et rend l'état **relu après coup**.
  ///
  /// Pas la valeur demandée : `register()` peut échouer — l'utilisateur a pu interdire le
  /// lancement automatique depuis les Réglages Système, et l'application ne passe pas
  /// outre. Rendre ce qu'on a demandé afficherait un interrupteur allumé devant un
  /// système qui a dit non.
  ///
  /// `SMAppService` demande macOS 13. En dessous il n'y a pas de remplacement pour une
  /// application en bac à sable — `SMLoginItemSetEnabled` ne vaut que pour un exécutable
  /// annexe, qu'il faudrait écrire, signer et embarquer. On rend `false`, et l'écran le
  /// dit plutôt que de laisser un interrupteur qui retombe sans un mot.
  private static func inscrire(_ valeur: Bool) -> Bool {
    guard #available(macOS 13.0, *) else { return false }
    do {
      if valeur {
        try SMAppService.mainApp.register()
      } else {
        try SMAppService.mainApp.unregister()
      }
    } catch {
      // On ne conclut pas sur l'exception : l'état se relit juste en dessous.
    }
    return inscrit()
  }

  private static func inscrit() -> Bool {
    guard #available(macOS 13.0, *) else { return false }
    return SMAppService.mainApp.status == .enabled
  }
}
