import AppKit
import FlutterMacOS
import Foundation
import ServiceManagement
import UserNotifications

/// Ce que les rappels demandent au système et que le greffon ne sait pas faire ici.
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
/// moyen, et c'est la première moitié de ce fichier.
///
/// ─── La seconde : dire pourquoi, et où aller ───
///
/// `requestPermissions` rend un simple `false`, et ce `false` recouvre deux situations qui
/// ne se corrigent pas du tout de la même façon : on vient de refuser l'alerte, ou macOS
/// ne l'a **jamais posée** parce qu'un refus est déjà enregistré. Dans le second cas,
/// l'alerte ne reparaîtra plus jamais — le système n'en présente qu'une par application —
/// et l'utilisateur doit passer par les Réglages Système.
///
/// Mesuré le 2026-10-20 : `UNErrorDomain` code 1, « Notifications are not allowed for this
/// application », `authorizationStatus` déjà à `.denied` avant toute demande. L'écran
/// disait alors « autorisez-les dans les réglages du système » sans rien de cliquable, et
/// l'application n'était pas davantage listée dans ces réglages. Un cul-de-sac.
///
/// [etatDesNotifications] distingue les deux, et [ouvrirLesReglagesDesNotifications] mène
/// à l'endroit exact plutôt qu'à la racine des Réglages Système.
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
      case "etatDesNotifications":
        etatDesNotifications(repondre)
      case "ouvrirLesReglagesDesNotifications":
        repondre(ouvrirLesReglagesDesNotifications())
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

  // MARK: - Le droit de notifier

  /// L'état du droit, **tel que le système le donne** — jamais ce que l'application croit.
  ///
  /// Les quatre cas d'`UNAuthorizationStatus`, rendus par leur nom plutôt que par leur
  /// rang : un entier se recopierait de travers le jour où Apple en ajoute un, et sans
  /// rien casser à la compilation.
  private static func etatDesNotifications(_ repondre: @escaping FlutterResult) {
    UNUserNotificationCenter.current().getNotificationSettings { reglages in
      let etat: String
      switch reglages.authorizationStatus {
      case .notDetermined: etat = "jamaisDemande"
      case .denied: etat = "refuse"
      case .authorized: etat = "accorde"
      case .provisional: etat = "provisoire"
      @unknown default: etat = "inconnu"
      }
      DispatchQueue.main.async { repondre(etat) }
    }
  }

  /// Ouvre le volet **des notifications**, pas la racine des Réglages Système.
  ///
  /// L'URL est celle de l'extension de réglages, et elle n'est pas devinée : la racine
  /// laisserait chercher parmi trente volets quelqu'un à qui on vient de dire que sa
  /// fonction est bloquée.
  ///
  /// macOS ne rend rien d'utile quand l'URL n'ouvre rien ; on rend ce que dit `NSWorkspace`
  /// pour que l'écran puisse se taire plutôt que de promettre un volet qui ne s'est pas
  /// ouvert.
  private static func ouvrirLesReglagesDesNotifications() -> Bool {
    guard let url = URL(
      string: "x-apple.systempreferences:com.apple.Notifications-Settings.extension")
    else { return false }
    return NSWorkspace.shared.open(url)
  }

  // MARK: - L'ouverture de session

  private static func inscrit() -> Bool {
    guard #available(macOS 13.0, *) else { return false }
    return SMAppService.mainApp.status == .enabled
  }
}
