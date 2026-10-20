import Cocoa
import FlutterMacOS
import workmanager_apple

@main
class AppDelegate: FlutterAppDelegate {
  override func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
    return true
  }

  override func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
    return true
  }

  /// Deux choses, avant que la fenêtre existe.
  ///
  /// **Les greffons du moteur sans écran.** Le rafraîchissement des rappels tourne dans un
  /// isolat de fond, que `workmanager` démarre avec un moteur Flutter neuf. Ce moteur-là
  /// n'a aucun greffon tant qu'on ne lui en donne pas : `Trousseau.lire` y lèverait une
  /// `MissingPluginException`, la tâche échouerait, et le seul signe en serait une ligne
  /// de journal. Les rappels resteraient ceux de la dernière ouverture de l'application,
  /// sans que rien ne le dise.
  ///
  /// **La nature du lancement**, lue ici parce que l'événement Apple qui la porte n'est
  /// disponible qu'à cet instant.
  ///
  /// `override` et `super` : `FlutterAppDelegate` **implémente** ce point d'entrée, bien
  /// que son en-tête ne le déclare pas — il n'y promet que `NSApplicationDelegate` et
  /// `FlutterAppLifecycleProvider`. Lire l'en-tête ne suffisait donc pas ; l'omission se
  /// solde par « overriding declaration requires an 'override' keyword », et sauter
  /// `super` priverait en silence le moteur de son propre démarrage.
  override func applicationWillFinishLaunching(_ notification: Notification) {
    super.applicationWillFinishLaunching(notification)
    WorkmanagerPlugin.setPluginRegistrantCallback { registry in
      RegisterGeneratedPlugins(registry: registry)
    }
    lanceeParLOuvertureDeSession = Self.lancementAutomatique()
  }

  /// L'application a-t-elle été lancée par l'ouverture de session plutôt que par
  /// quelqu'un ?
  ///
  /// Lue avant que la fenêtre paraisse, et consommée par `MainFlutterWindow` : au
  /// démarrage de la session, GhostCal doit se taire. Une application de rappels qui ouvre
  /// un coffre verrouillé en plein écran chaque matin se fait retirer des éléments
  /// d'ouverture avant la fin de la semaine — en emportant les rappels avec elle.
  private(set) var lanceeParLOuvertureDeSession = false

  /// L'événement Apple que `loginwindow` envoie, et le seul moyen fiable de distinguer
  /// les deux lancements.
  ///
  /// `ProcessInfo.arguments` ne porte rien : `SMAppService.mainApp` lance le paquet tel
  /// quel, sans drapeau. `NSApplicationLaunchIsDefaultLaunchKey` ne distingue pas non plus
  /// — il vaut `true` dans les deux cas, et ne devient faux que pour une ouverture de
  /// document. Reste le descripteur `keyAEPropData` de l'événement d'ouverture, posé à
  /// `keyAELaunchedAsLogInItem`.
  private static func lancementAutomatique() -> Bool {
    guard let evenement = NSAppleEventManager.shared().currentAppleEvent,
      evenement.eventID == kAEOpenApplication,
      let propriete = evenement.paramDescriptor(forKeyword: keyAEPropData)
    else { return false }
    return propriete.enumCodeValue == keyAELaunchedAsLogInItem
  }
}
