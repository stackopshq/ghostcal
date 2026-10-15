import Cocoa
import FlutterMacOS

class MainFlutterWindow: NSWindow {
  /// Ce en dessous de quoi la fenêtre ne descend pas.
  ///
  /// Une fenêtre macOS se redimensionne jusqu'au timbre-poste si on ne l'en empêche pas,
  /// et la mise en page ne proteste pas : elle se tasse, puis déborde, et Flutter peint
  /// une bande jaune et noire à la place de ce qui ne tient plus. Le gabarit de
  /// `flutter create` ne pose aucune borne.
  ///
  /// Les deux nombres sont mesurés sur ce que l'application contient, pas choisis :
  ///
  /// · **720 de large** — la grille de la semaine est le plus large de tous les écrans :
  ///   une gouttière d'heures de 52 points, puis sept colonnes. En dessous d'une
  ///   centaine de points par colonne, un titre de rendez-vous ne tient plus sur un mot.
  ///   720 laisse 95 points par jour, et la barre d'onglets ses cinq libellés entiers.
  ///
  /// · **560 de haut** — la carte de verre de l'écran d'entrée, enseigne comprise, plus
  ///   ses marges. C'est le seul écran dont la hauteur ne se fait pas par défilement :
  ///   plus court, le bouton « Déverrouiller » passe sous le bord.
  static let tailleMinimale = NSSize(width: 720, height: 560)

  /// L'ouverture par défaut. Plus grande que le minimum : une fenêtre qui s'ouvre à sa
  /// taille minimale donne l'impression d'un outil à l'étroit, et la semaine y est
  /// lisible sans qu'on ait à tirer un coin. Le gabarit ouvrait à 800 × 600, ce qui
  /// convient à une démonstration et pas à un agenda.
  ///
  /// macOS retient ensuite la taille choisie par l'utilisateur — `setFrameAutosaveName`
  /// ci-dessous —, et cette valeur ne sert plus qu'au tout premier lancement.
  static let tailleParDefaut = NSSize(width: 1100, height: 760)

  override func awakeFromNib() {
    let flutterViewController = FlutterViewController()
    let windowFrame = self.frame
    self.contentViewController = flutterViewController
    self.setFrame(windowFrame, display: true)

    self.contentMinSize = MainFlutterWindow.tailleMinimale
    // `setContentSize` et non `setFrame` : la hauteur voulue est celle du contenu, et la
    // barre de titre s'ajoute par-dessus. L'écrire en `frame` rognerait 28 points à
    // chaque mesure ci-dessus.
    self.setContentSize(MainFlutterWindow.tailleParDefaut)
    self.center()
    // Après `center()` : macOS restitue alors la position et la taille de la dernière
    // session, et n'utilise les deux appels précédents que lorsqu'il n'a rien à restituer.
    self.setFrameAutosaveName("GhostCal.fenetre")

    RegisterGeneratedPlugins(registry: flutterViewController)

    super.awakeFromNib()
  }
}
