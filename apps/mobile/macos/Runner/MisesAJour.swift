import AppKit
import Sparkle

/// Les mises à jour, sans repasser par le site.
///
/// ─── Pourquoi ce fichier existe ───
///
/// GhostCal macOS se distribue hors App Store : une image disque qu'on télécharge, et
/// rien derrière. Chaque correctif demandait donc de retourner sur le site, de
/// retélécharger vingt-sept mégaoctets et de glisser l'application par-dessus l'ancienne.
/// Personne ne le fait, et le parc installé vieillit en silence — y compris pour un
/// correctif de sécurité.
///
/// Sparkle est ce qu'emploient la plupart des applications macOS distribuées ainsi.
///
/// ─── Ce qu'il fait, et ce qu'il ne fait pas ───
///
/// Il vérifie une fois par jour, et **propose**. Jamais d'installation sans un clic :
/// une application qui vend la confidentialité et qui remplace son propre binaire sans
/// qu'on ait rien demandé envoie un drôle de message, et on ne saurait plus dire quelle
/// version tourne. Les deux réglages qui le disent sont dans `Info.plist`,
/// `SUEnableAutomaticChecks` et `SUAutomaticallyUpdate`.
///
/// Chaque mise à jour est signée par une clé Ed25519 **propre à Sparkle**, qui n'a rien à
/// voir avec le certificat Developer ID : celui-ci dit qui a produit l'application, celle-là
/// dit que ce flux-ci vient bien de nous. Un serveur qui servirait le site ne pourrait pas
/// pour autant pousser un binaire. La moitié publique est dans `Info.plist` ; la privée
/// vit dans le Bao, sous `kv/ghostcal/sparkle`.
///
/// ─── Le bac à sable ───
///
/// Une application sandboxée ne peut pas se remplacer elle-même. Sparkle passe par deux
/// services XPC embarqués dans son cadriciel, que les `.entitlements` autorisent nommément.
/// Sans ces deux lignes, la recherche fonctionne, le téléchargement aussi, et
/// l'installation échoue à la fin — le pire ordre possible.
enum MisesAJour {
  /// Démarré dès sa création : c'est ce que fait `startingUpdater: true`, et c'est ce qui
  /// pose la vérification périodique. Le laisser à `false` donnerait un menu qui répond et
  /// une application qui ne vérifie jamais d'elle-même.
  ///
  /// `static let` et non une propriété d'`AppDelegate` : l'objet doit vivre aussi longtemps
  /// que l'application. Relâché, il emporte sa minuterie avec lui, et la vérification
  /// s'arrête sans que rien ne le dise.
  static let controleur = SPUStandardUpdaterController(
    startingUpdater: true,
    updaterDelegate: nil,
    userDriverDelegate: nil
  )
}
