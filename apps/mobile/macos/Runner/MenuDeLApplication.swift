import AppKit
import FlutterMacOS

/// Rendre vivants les items de la barre de menus que le gabarit laisse inertes.
///
/// ─── Pourquoi ⌘, mérite ce fichier ───
///
/// Sur un Mac, ⌘, ouvre les réglages. Ce n'est pas une préférence d'utilisateur, c'est un
/// réflexe : on l'essaie avant de chercher un bouton. Le `MainMenu.xib` de Flutter porte
/// déjà l'item « Réglages… » avec son `keyEquivalent=","` — mais **sans connexion**. Il
/// est donc là, grisé, depuis le premier jour, et le raccourci ne fait rien.
///
/// Depuis que les réglages ont quitté la barre d'onglets pour un menu dessiné par
/// l'application, le défaut se voit davantage : le chemin standard du système ne mène
/// nulle part pendant que le chemin maison mène partout.
///
/// ─── Branché en Swift, pas dans le nib ───
///
/// On pourrait connecter l'item dans Interface Builder. Modifier les connexions d'un xib
/// à la main, hors de l'éditeur, est une opération qu'on relit mal et qu'un conflit de
/// fusion rend illisible. Ici, trois lignes de Swift disent la même chose et se relisent.
///
/// ─── L'item se trouve par son raccourci, pas par son titre ───
///
/// Son titre est traduit — « Preferences… », « Réglages… » —, donc le chercher par le
/// texte ne marcherait que dans une langue. `keyEquivalent == ","` dans le menu de
/// l'application **est** la définition de ce qu'on cherche : l'item que ⌘, déclenche.
final class MenuDeLApplication: NSObject {
  static let partage = MenuDeLApplication()

  private var canal: FlutterMethodChannel?

  /// Le canal est celui qu'écoute `ecrans/accueil.dart`, méthode `reglages`.
  func brancher(_ registrar: FlutterPluginRegistrar) {
    canal = FlutterMethodChannel(
      name: "ch.stackops.ghostcal/menu", binaryMessenger: registrar.messenger)
  }

  /// À appeler une fois la barre de menus chargée — voir `MainFlutterWindow`.
  ///
  /// Ne fait rien si l'item est introuvable : une barre de menus sans item de réglages
  /// est inhabituelle mais pas fautive, et faire échouer le lancement pour un raccourci
  /// serait disproportionné.
  func brancherLesReglages() {
    guard let item = itemDesReglages() else { return }
    item.target = self
    item.action = #selector(ouvrirLesReglages)
    // L'item du gabarit est désactivé faute de cible ; lui en donner une le rallume, mais
    // seulement parce qu'`autoenablesItems` suit la présence d'une action. On l'écrit
    // quand même : le jour où quelqu'un coupe l'activation automatique, l'item resterait
    // gris sans que rien ne le dise.
    item.isEnabled = true
  }

  private func itemDesReglages() -> NSMenuItem? {
    guard let menuDeLApplication = NSApp.mainMenu?.items.first?.submenu else { return nil }
    return menuDeLApplication.items.first {
      $0.keyEquivalent == "," && $0.keyEquivalentModifierMask == .command
    }
  }

  @objc private func ouvrirLesReglages() {
    canal?.invokeMethod("reglages", arguments: nil)
  }
}
