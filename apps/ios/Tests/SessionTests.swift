import XCTest

@testable import Ghostcal

/// Ce qui décide, dans la tranche d'authentification.
///
/// Les écrans ne sont pas testés ici : ils se regardent. Ce qui se vérifie, c'est ce
/// qu'ils appellent — l'adresse qu'on accepte, et la distinction entre « pas connecté »
/// et « connecté mais coffre fermé ». Confondre ces deux-là renverrait à l'écran de
/// connexion quelqu'un de parfaitement authentifié, sans lui dire que c'est sa phrase qui
/// ne va pas.
final class SessionTests: XCTestCase {

    // ─── L'adresse du serveur ───

    /// Taper un nom d'hôte nu est le geste naturel. Le refuser ferait échouer la toute
    /// première tentative de quelqu'un qui a pourtant donné la bonne adresse.
    func testUnHoteNuDevientDuHttps() {
        XCTAssertEqual(
            AdresseDeServeur.normaliser("ghostcal.stackops.ch")?.absoluteString,
            "https://ghostcal.stackops.ch")
    }

    /// Sauf en boucle locale, où un serveur de développement tourne en clair. Le deviner
    /// évite d'obliger à taper « http:// » précisément là où on développe.
    func testLaBoucleLocaleResteEnClair() {
        for adresse in ["localhost:5173", "127.0.0.1:8080", "localhost"] {
            XCTAssertEqual(
                AdresseDeServeur.normaliser(adresse)?.scheme, "http",
                "« \(adresse) » est une boucle locale")
        }
    }

    /// Un hôte distant tapé sans schéma ne doit jamais devenir du clair par défaut : les
    /// jetons de session et tout ce qui suit y passeraient en lisible.
    func testUnHoteDistantNeDevientJamaisDuClair() {
        XCTAssertEqual(AdresseDeServeur.normaliser("192.168.1.50:8080")?.scheme, "https")
        XCTAssertEqual(AdresseDeServeur.normaliser("ghostcal.example.com")?.scheme, "https")
    }

    func testUnSchemaExpliciteEstConserve() {
        XCTAssertEqual(
            AdresseDeServeur.normaliser("http://ghostcal.example.com")?.scheme, "http")
    }

    func testCeQuiNEstPasUneAdresseEstRefuse() {
        for saisie in ["", "   ", "ftp://ghostcal.example.com", "https://", "://x"] {
            XCTAssertNil(
                AdresseDeServeur.normaliser(saisie), "« \(saisie) » n'est pas une adresse")
        }
    }

    // ─── Les trois états ───

    /// « Connecté » et « coffre ouvert » sont deux choses distinctes. L'égalité doit les
    /// séparer, sinon un écran qui compare deux états prendrait un coffre fermé pour une
    /// déconnexion — et redemanderait une adresse et un compte déjà donnés.
    @MainActor
    func testLesTroisEtatsSeDistinguent() {
        XCTAssertNotEqual(SessionStore.Etat.dehors, .coffreFerme(raison: nil))
        XCTAssertNotEqual(SessionStore.Etat.coffreFerme(raison: nil), .ouvert)
        XCTAssertNotEqual(SessionStore.Etat.dehors, .ouvert)
        XCTAssertEqual(SessionStore.Etat.coffreFerme(raison: "x"), .coffreFerme(raison: "x"))
        XCTAssertNotEqual(SessionStore.Etat.coffreFerme(raison: "x"), .coffreFerme(raison: nil))
    }

    @MainActor
    func testUneSessionNeuveEstDehors() {
        Trousseau.toutRetirer()
        XCTAssertEqual(SessionStore().etat, .dehors)
        XCTAssertFalse(SessionStore().sessionEnregistree)
    }

    // ─── Le trousseau ───

    /// Ce qu'on y pose se relit, et ce qu'on en retire disparaît. Un jeton qui survivrait
    /// à la déconnexion rouvrirait le compte au prochain lancement.
    func testLeTrousseauPoseEtRetire() {
        let cle = "ghostcal.essai.\(UUID().uuidString)"
        Trousseau.poser("valeur", pour: cle)
        XCTAssertEqual(Trousseau.lire(cle), "valeur")
        Trousseau.poser("autre", pour: cle)
        XCTAssertEqual(Trousseau.lire(cle), "autre", "poser deux fois ne doit pas dupliquer")
        Trousseau.retirer(cle)
        XCTAssertNil(Trousseau.lire(cle))
    }
}
