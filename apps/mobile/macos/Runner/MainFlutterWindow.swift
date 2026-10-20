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
  /// · **560 de haut** — l'écran d'entrée y montre son enseigne, les deux champs et le
  ///   bouton « Déverrouiller » ; la ligne Touch ID passe sous le bord, et c'est sans
  ///   conséquence, la carte défilant. L'agenda, lui, garde quatre heures de grille
  ///   au-dessus de la barre d'onglets — relevé sur la capture
  ///   `05-agenda-en-sombre-petite`, qui est prise à cette taille exacte.
  ///
  ///   Un minimum est un plancher, pas une taille confortable : il doit interdire
  ///   l'illisible, pas imposer l'agréable. L'ouverture par défaut, plus bas, s'en charge.
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
    // Hors du registre engendré, qui est réécrit à chaque `flutter pub get` : ce qu'on y
    // ajouterait serait effacé sans message, et la photo de profil cesserait de partir
    // pour une raison introuvable dans l'historique.
    Vignette.enregistrer(flutterViewController.registrar(forPlugin: "Vignette"))
    OuvertureDeSession.enregistrer(
      flutterViewController.registrar(forPlugin: "OuvertureDeSession"))
    MenuDeLApplication.partage.brancher(
      flutterViewController.registrar(forPlugin: "MenuDeLApplication"))

    super.awakeFromNib()

    // ─── Au démarrage de la session, GhostCal se tait ───
    //
    // L'application s'inscrit aux ouvertures de session pour une seule raison : rendre au
    // rafraîchissement des rappels l'occasion de tourner, `NSBackgroundActivityScheduler`
    // ne réveillant rien. Ce travail n'a besoin d'aucune fenêtre.
    //
    // En ouvrir une poserait un coffre verrouillé en plein écran chaque matin, devant
    // quelqu'un qui n'a rien demandé — et le réglage serait retiré avant la fin de la
    // semaine, emportant les rappels avec lui.
    //
    // `orderOut` et non `miniaturize` : une fenêtre réduite laisse une vignette dans le
    // Dock, ce qui est le même dérangement en plus petit. L'icône du Dock reste, elle, et
    // c'est par elle qu'on revient.
    //
    // Après `super.awakeFromNib()`, sans quoi la fin du chargement du nib remettrait la
    // fenêtre au premier plan juste derrière.
    if (NSApp.delegate as? AppDelegate)?.lanceeParLOuvertureDeSession == true {
      self.orderOut(nil)
    }

    // ─── Le menu, au tour de boucle suivant ───
    //
    // La fenêtre et la barre de menus sortent du **même** nib, et rien ne garantit que
    // `NSApp.mainMenu` soit déjà posé quand cette fenêtre s'éveille : l'ordre d'éveil des
    // objets de premier niveau n'est pas spécifié. Brancher ici tout de suite marcherait
    // la plupart du temps, ce qui est la pire des propriétés — ⌘, serait inerte une fois
    // sur dix, chez quelqu'un d'autre.
    //
    // Un passage par la file principale suffit : le chargement du nib est terminé quand
    // ce bloc s'exécute.
    DispatchQueue.main.async {
      MenuDeLApplication.partage.brancherLesReglages()
    }
  }
}
