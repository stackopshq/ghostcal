import Foundation

/// Ce que l'application garde entre deux lancements.
///
/// Les jetons de session vivent ici et nulle part ailleurs : ni dans les préférences, ni
/// dans un fichier. `WhenUnlockedThisDeviceOnly` ferme deux portes d'un coup — rien n'est
/// lisible tant que l'appareil est verrouillé, et rien ne part dans une sauvegarde ni
/// vers un autre appareil par restauration.
///
/// **La phrase de chiffrement n'est jamais rangée.** C'est elle qui dérive la clé du
/// coffre ; la garder reviendrait à laisser le coffre ouvert en permanence, ce qui vide de
/// son sens le fait qu'il soit chiffré. On la redemande à chaque ouverture.
enum Trousseau {
    enum Cle {
        static let jetonDAcces = "ghostcal.acces"
        static let jetonDeRafraichissement = "ghostcal.rafraichissement"
        static let serveur = "ghostcal.serveur"
        static let email = "ghostcal.email"
    }

    static func poser(_ valeur: String, pour cle: String) {
        retirer(cle)
        let requete: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: cle,
            kSecValueData as String: Data(valeur.utf8),
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        ]
        SecItemAdd(requete as CFDictionary, nil)
    }

    static func lire(_ cle: String) -> String? {
        let requete: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: cle,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var resultat: AnyObject?
        guard SecItemCopyMatching(requete as CFDictionary, &resultat) == errSecSuccess,
            let data = resultat as? Data
        else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func retirer(_ cle: String) {
        SecItemDelete(
            [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrAccount as String: cle,
            ] as CFDictionary)
    }

    static func toutRetirer() {
        [Cle.jetonDAcces, Cle.jetonDeRafraichissement, Cle.serveur, Cle.email].forEach(retirer)
    }
}
