import XCTest

@testable import Ghostcal

/// Le cœur commun est-il réellement joignable depuis l'application ?
///
/// Ce n'est pas une vérification de la cryptographie — elle est éprouvée dans le cœur,
/// contre des vecteurs produits par le navigateur. C'est une vérification de la
/// **liaison** : que l'XCFramework est lié, que les liaisons Swift sont compilées, et
/// qu'un appel traverse la frontière et revient.
///
/// Sans ce test, une chaîne de construction cassée se manifesterait au premier
/// déverrouillage d'un utilisateur, pas à la compilation.
final class CoeurTests: XCTestCase {

    func testLaDerivationTraverseLaFrontiere() throws {
        // Le vecteur vient de `hash-wasm`, la bibliothèque Argon2 du navigateur, et non
        // du cœur : le même que celui qui garde le cœur honnête côté Rust.
        let sel = Data(repeating: 7, count: 16)
        let cle = try deriverCle(phrase: "correct horse", sel: sel)
        let hexa = cle.map { String(format: "%02x", $0) }.joined()
        XCTAssertEqual(
            hexa, "7b985d8fa00c9eccccf918c8cb9feaa8036af381caf6f498e099b5b849b8c18a",
            "la clé dérivée diffère de celle du navigateur : ce que le web a scellé ne "
                + "s'ouvrirait pas ici")
    }

    func testUnSceauFaitLAllerRetour() throws {
        let paire = genererPaire()
        let scelle = try scellerVers(
            publique: paire.publique, clair: Data("rendez-vous".utf8),
            domaine: "ghostcal-zk-v1")
        let ouvert = try ouvrirSceau(
            privee: paire.privee, blob: scelle, domaine: "ghostcal-zk-v1")
        XCTAssertEqual(String(data: ouvert, encoding: .utf8), "rendez-vous")
    }

    func testLeDomaineSepareLesProduits() throws {
        // Un seul cœur sert ghostcal et ghostmail ; c'est le domaine qui les empêche de
        // lire les données l'un de l'autre. Si cette séparation cédait, elle céderait en
        // silence — d'où ce test.
        let paire = genererPaire()
        let scelle = try scellerVers(
            publique: paire.publique, clair: Data("agenda".utf8), domaine: "ghostcal-zk-v1")
        XCTAssertThrowsError(
            try ouvrirSceau(privee: paire.privee, blob: scelle, domaine: "ghostmail-zk-v1"),
            "un autre produit ne doit pas ouvrir ce sceau")
    }

    func testLaTailleDuSelEstImposee() {
        // Le sel fait 16 octets côté web. En accepter d'autres produirait des clés que le
        // navigateur ne saurait pas reproduire.
        XCTAssertThrowsError(try deriverCle(phrase: "x", sel: Data(repeating: 0, count: 8)))
    }
}
