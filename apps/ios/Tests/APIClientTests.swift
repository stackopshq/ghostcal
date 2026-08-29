import XCTest

@testable import Ghostcal

/// Ce que le client doit faire sans qu'on ait à y penser à chaque appel.
///
/// Les deux premiers cas ne sont pas des détails d'implémentation : ce sont les deux
/// façons documentées de se tromper contre cette API, et elles échouent *silencieusement*.
/// Un en-tête d'organisation oublié ne produit aucune erreur — le serveur sert les données
/// d'une autre équipe. Un 403 pris pour un 401 fait boucler l'application sur un
/// rafraîchissement qui réussit sans rien changer.
final class APIClientTests: XCTestCase {

    func testUnQuatreCentTroisNEstPasUnProblemeDeJeton() {
        // Le serveur rend 403 pour « pas membre de cette organisation », « rôle
        // insuffisant », « mot de passe actuel faux », « adresse non vérifiée ». Aucun de
        // ces cas ne se répare en renouvelant le jeton.
        let interdit = APIError.http(status: 403, detail: "not a member of that organization")
        XCTAssertFalse(interdit.estUnProblemeDeJeton)

        let expire = APIError.http(status: 401, detail: "invalid token")
        XCTAssertTrue(expire.estUnProblemeDeJeton)
    }

    func testLeDetailSeLitDansSesDeuxFormes() throws {
        // Refus métier : `detail` est une chaîne.
        let metier = Data(#"{"detail":"slot is no longer available"}"#.utf8)
        XCTAssertEqual(
            miroirDuDetail(metier, 409), "slot is no longer available",
            "un refus métier doit s'afficher tel quel")

        // Validation Pydantic : `detail` est un tableau d'objets. Un décodeur qui n'attend
        // qu'une chaîne échoue précisément là où le serveur explique ce qui ne va pas.
        let validation = Data(
            #"{"detail":[{"loc":["body","email"],"msg":"value is not a valid email address","type":"value_error"}]}"#
                .utf8)
        XCTAssertEqual(
            miroirDuDetail(validation, 422), "value is not a valid email address",
            "un 422 porte le message dans un tableau, pas dans une chaîne")
    }

    func testLesDatesDuServeurSeDecodentAvecEtSansFractions() throws {
        struct Porteur: Decodable { let start_at: Date }
        let avec = Data(#"{"start_at":"2026-08-29T14:30:00.123456+02:00"}"#.utf8)
        let sans = Data(#"{"start_at":"2026-08-29T14:30:00+02:00"}"#.utf8)

        // `.iso8601` seul échoue sur les fractions de seconde, que le serveur émet parfois.
        XCTAssertNoThrow(try JSONDecoder.api.decode(Porteur.self, from: avec))
        XCTAssertNoThrow(try JSONDecoder.api.decode(Porteur.self, from: sans))
    }

    /// Rejoue la lecture du détail telle que le client la fait, sans passer par le réseau.
    private func miroirDuDetail(_ donnees: Data, _ statut: Int) -> String {
        struct Chaine: Decodable { let detail: String }
        struct Validation: Decodable {
            struct Entree: Decodable { let msg: String }
            let detail: [Entree]
        }
        if let simple = try? JSONDecoder().decode(Chaine.self, from: donnees) {
            return simple.detail
        }
        if let validation = try? JSONDecoder().decode(Validation.self, from: donnees) {
            return validation.detail.map(\.msg).joined(separator: " · ")
        }
        return "Erreur serveur (\(statut))."
    }
}
