import AppKit
import FlutterMacOS
import Sparkle

/// La barre de menus de l'application : celle du gabarit, rendue vivante, et ce qui manque.
///
/// ─── Pourquoi une barre de menus, alors que l'écran a déjà tout ───
///
/// Parce que sur un Mac on l'essaie. ⌘, pour les réglages, ⌘N pour créer, ⌘F pour
/// chercher : ce sont des réflexes, tentés avant qu'on cherche un bouton. Le `MainMenu.xib`
/// de Flutter porte déjà « Réglages… » et « Rechercher… » avec leurs équivalents clavier —
/// **et aucune connexion derrière**. Ils sont là, grisés, depuis le premier jour. Un
/// chemin standard qui ne mène nulle part est pire qu'un chemin absent : on l'essaie, et
/// on conclut que l'application est cassée.
///
/// ─── Deux gestes, et ils ne se valent pas ───
///
/// **Câbler** ce qui existe : « Réglages… » (⌘,) et « Rechercher… » (⌘F) sont dans le nib,
/// traduits, à leur place canonique. Leur donner une cible suffit, et évite surtout de
/// créer un second item portant le même équivalent clavier — AppKit en choisirait un, et
/// pas forcément le nôtre.
///
/// **Construire** ce qui manque : il n'y a pas de menu « Fichier » dans le gabarit, et
/// « Présentation » ne contient que le plein écran. Ceux-là sont montés en Swift.
///
/// ─── Les menus sont trouvés par leurs actions, jamais par leurs titres ───
///
/// Les titres sont traduits. Chercher « View » ne marcherait que sur un système anglais,
/// et le défaut serait invisible ici. Un sélecteur — `toggleFullScreen:`, `copy:` — ne
/// change pas avec la langue, et il **définit** le menu qu'on cherche.
///
/// ─── Ce que ces menus ne font pas ───
///
/// Ils suivent la langue du **système**, pas le réglage de langue de l'application : la
/// barre est construite avant que Flutter démarre, et le réglage peut changer en cours de
/// route. Un Mac anglais avec GhostCal en français aura des menus anglais. C'est déjà le
/// cas des menus du gabarit, et ça ne se rattrape pas sans reconstruire la barre à chaque
/// changement de langue — pour un gain que personne n'a demandé.
final class MenuDeLApplication: NSObject {
  static let partage = MenuDeLApplication()

  /// Le canal qu'écoute `ecrans/accueil.dart`. Les noms de méthode viennent de là :
  /// `vue` (argument `jour|semaine|mois|liste`), `aujourdhui`, `precedent`, `suivant`,
  /// `nouveau`, `rechercher`, `reglages`.
  private var canal: FlutterMethodChannel?

  func brancher(_ registrar: FlutterPluginRegistrar) {
    canal = FlutterMethodChannel(
      name: "ch.stackops.ghostcal/menu", binaryMessenger: registrar.messenger)
  }

  /// À appeler une fois la barre de menus chargée — voir `MainFlutterWindow`.
  /// Monté une fois. Le drapeau est explicite plutôt que déduit de l'état de la barre :
  /// la première version cherchait son propre sélecteur pour savoir si le travail était
  /// fait — or `cablerLExistant()` vient de le poser sur « Réglages… », donc la garde
  /// était toujours vraie et le menu « Fichier » n'était jamais créé. Déduire une
  /// présence d'un effet qu'on vient soi-même de produire est une boucle qu'on ne voit
  /// pas en relisant.
  private var monte = false

  func monter() {
    guard !monte else { return }
    monte = true
    cablerLExistant()
    poserLaRechercheDeMisesAJour()
    monterLeMenuFichier()
    garnirLeMenuPresentation()
  }

  // MARK: - Câbler ce que le gabarit laisse inerte

  private func cablerLExistant() {
    // Par équivalent clavier et non par titre : « Réglages… » / « Preferences… » et
    // « Rechercher… » / « Find… » sont traduits, mais ⌘, et ⌘F ne le sont pas.
    if let reglages = itemDuMenuDeLApplication(touche: ",") {
      brancher(reglages, methode: "reglages")
    }
    // ⌘F est porté par « Rechercher… » du sous-menu Rechercher, dont l'action
    // `performFindPanelAction:` ne trouve aucun répondant : l'item est grisé et la touche
    // ne fait rien. On le détourne plutôt que d'ajouter un second ⌘F ailleurs.
    //
    // « Passer en plein écran » porte ⌃⌘F et n'entre donc pas en conflit — vérifié dans
    // le nib, pas supposé.
    if let rechercher = itemParTouche("f", dans: menuContenant(#selector(NSText.copy(_:)))) {
      brancher(rechercher, methode: "rechercher")
    }
  }

  private func brancher(_ item: NSMenuItem, methode: String, argument: String? = nil) {
    item.target = self
    item.action = #selector(envoyer(_:))
    item.representedObject = Commande(methode: methode, argument: argument)
    item.isEnabled = true
  }

  /// « Rechercher les mises à jour… », juste sous « À propos ».
  ///
  /// C'est là que macOS le met, dans toutes les applications qui en ont un — assez
  /// haut pour qu'on le trouve sans le chercher, et pas dans les Réglages, où il
  /// passerait pour une préférence.
  ///
  /// L'item vise directement le contrôleur de Sparkle : rien ne transite par Flutter.
  /// Une vérification de mise à jour n'a aucun état à partager avec les écrans, et
  /// l'envoyer sur le canal ajouterait un aller-retour pour revenir au même endroit.
  ///
  /// Posé en seconde position plutôt qu'après un séparateur cherché : les menus du
  /// gabarit n'ont pas d'identifiant, et viser « l'item qui suit celui dont le
  /// sélecteur est `orderFrontStandardAboutPanel:` » reviendrait à deviner.
  private func poserLaRechercheDeMisesAJour() {
    guard let menu = NSApp.mainMenu?.items.first?.submenu else { return }
    let item = NSMenuItem(
      title: traduire("menu.misesAJour"),
      action: #selector(SPUStandardUpdaterController.checkForUpdates(_:)),
      keyEquivalent: ""
    )
    item.target = MisesAJour.controleur
    // Après « À propos », avant le premier séparateur du gabarit.
    menu.insertItem(item, at: min(1, menu.items.count))
    menu.insertItem(.separator(), at: min(2, menu.items.count))
  }

  // MARK: - Construire ce qui manque

  /// Le gabarit de Flutter n'a pas de menu « Fichier ». On l'insère après celui de
  /// l'application, à la place qu'il occupe dans toutes les applications du système.
  private func monterLeMenuFichier() {
    guard let barre = NSApp.mainMenu else { return }
    let titre = traduire("menu.fichier")
    let entree = NSMenuItem(title: titre, action: nil, keyEquivalent: "")
    let menu = NSMenu(title: titre)
    menu.addItem(nouvelItem("menu.nouvelEvenement", "n", methode: "nouveau"))
    menu.addItem(.separator())
    // Verrouiller a déjà son bouton dans la barre de l'agenda et sa ligne dans
    // Réglages → Sécurité ; ⌘L ne fait que lui donner le raccourci qu'on essaie.
    menu.addItem(nouvelItem("menu.verrouiller", "l", methode: "verrouiller"))
    entree.submenu = menu
    barre.insertItem(entree, at: 1)
  }

  /// « Présentation » existe et ne contient que le plein écran. Les vues et la navigation
  /// se posent **en tête**, avant lui, parce que c'est ce qu'on y cherche.
  private func garnirLeMenuPresentation() {
    guard let presentation = menuContenant(#selector(NSWindow.toggleFullScreen(_:))) else { return }
    let ajouts: [NSMenuItem] = [
      nouvelItem("menu.jour", "1", methode: "vue", argument: "jour"),
      nouvelItem("menu.semaine", "2", methode: "vue", argument: "semaine"),
      nouvelItem("menu.mois", "3", methode: "vue", argument: "mois"),
      nouvelItem("menu.liste", "4", methode: "vue", argument: "liste"),
      .separator(),
      nouvelItem("menu.aujourdhui", "t", methode: "aujourdhui"),
      // Les flèches, par leurs codes de touche de fonction : une chaîne vide donnerait un
      // item sans raccourci, en silence.
      nouvelItem("menu.periodePrecedente", String(format: "%C", 0xF702), methode: "precedent"),
      nouvelItem("menu.periodeSuivante", String(format: "%C", 0xF703), methode: "suivant"),
      .separator(),
    ]
    for (rang, item) in ajouts.enumerated() {
      presentation.insertItem(item, at: rang)
    }
  }

  /// ─── Les chiffres, sur un clavier qui n'en a pas à cet endroit ───
  ///
  /// `keyEquivalent: "1"` ne reste pas « 1 ». AppKit le **traduit** pour la disposition
  /// active : mesuré le 2026-10-20 sur ABC-AZERTY, l'item relit `keyEquivalent == "&"`,
  /// et la barre affiche ⌘&, ⌘É, ⌘", ⌘' pour Jour, Semaine, Mois, Liste. C'est ce qu'il
  /// faut : ce sont les caractères que portent physiquement les touches 1 à 4 ici, donc
  /// le menu annonce la frappe qu'on fait réellement.
  ///
  /// Et les deux frappes aboutissent — ⌘& comme ⌘1 (Maj compris) rendent « Jour ».
  /// Vérifié en instrumentant l'envoi, pas déduit : il aurait été aussi facile de croire
  /// que poser « 1 » sur un clavier français ne déclenche rien.
  private func nouvelItem(
    _ cle: String, _ touche: String, methode: String, argument: String? = nil
  ) -> NSMenuItem {
    let item = NSMenuItem(
      title: traduire(cle), action: #selector(envoyer(_:)), keyEquivalent: touche)
    item.keyEquivalentModifierMask = .command
    brancher(item, methode: methode, argument: argument)
    return item
  }

  // MARK: - L'envoi

  /// Ce qu'un item porte : de quoi appeler le canal, et rien d'autre.
  private final class Commande: NSObject {
    let methode: String
    let argument: String?
    init(methode: String, argument: String?) {
      self.methode = methode
      self.argument = argument
    }
  }

  @objc private func envoyer(_ item: NSMenuItem) {
    guard let commande = item.representedObject as? Commande else { return }
    canal?.invokeMethod(commande.methode, arguments: commande.argument)
  }

  // MARK: - Trouver

  private func traduire(_ cle: String) -> String {
    NSLocalizedString(cle, comment: "")
  }

  private func itemDuMenuDeLApplication(touche: String) -> NSMenuItem? {
    itemParTouche(touche, dans: NSApp.mainMenu?.items.first?.submenu)
  }

  /// Cherche en profondeur : « Rechercher… » vit dans un sous-menu de « Édition ».
  private func itemParTouche(_ touche: String, dans menu: NSMenu?) -> NSMenuItem? {
    guard let menu else { return nil }
    for item in menu.items {
      if item.keyEquivalent == touche && item.keyEquivalentModifierMask == .command {
        return item
      }
      if let trouve = itemParTouche(touche, dans: item.submenu) { return trouve }
    }
    return nil
  }

  /// Le menu de premier niveau qui contient un item portant cette action, à n'importe
  /// quelle profondeur. Les titres sont traduits ; les sélecteurs, non.
  private func menuContenant(_ action: Selector) -> NSMenu? {
    NSApp.mainMenu?.items.compactMap(\.submenu).first { contient(action, dans: $0) }
  }

  private func contient(_ action: Selector, dans menu: NSMenu) -> Bool {
    menu.items.contains { item in
      item.action == action || (item.submenu.map { contient(action, dans: $0) } ?? false)
    }
  }
}
