import XCTest

@testable import Ghostcal

/// Ce qui décide, dans les tâches : l'ordre d'affichage et la lecture du contenu scellé.
final class TachesTests: XCTestCase {

    private func tache(
        _ titre: String, echeance: Date? = nil, faite: Bool = false,
        creee: Date = Date(timeIntervalSince1970: 1_788_000_000)
    ) -> Tache {
        Tache(
            id: UUID(), titre: .dechiffre(titre), notes: nil, echeance: echeance, faite: faite,
            creee: creee)
    }

    // ─── L'ordre ───

    /// Ce qui presse d'abord, ce qui est fait à la fin. Le serveur ne peut pas trier sur
    /// le titre — il ne le lit pas — donc tout se joue ici.
    func testCeQuiEstFaitPasseApresCeQuiResteAFaire() {
        let ordonnees = Taches.ordonner([
            tache("faite", faite: true), tache("à faire"),
        ])
        XCTAssertEqual(ordonnees.first?.faite, false)
        XCTAssertEqual(ordonnees.last?.faite, true)
    }

    func testLesEcheancesLesPlusProchesRemontent() {
        let demain = Date(timeIntervalSince1970: 1_788_100_000)
        let semaineProchaine = Date(timeIntervalSince1970: 1_788_600_000)
        let ordonnees = Taches.ordonner([
            tache("plus tard", echeance: semaineProchaine),
            tache("bientôt", echeance: demain),
        ])
        XCTAssertEqual(ordonnees.first?.echeance, demain)
    }

    /// Une tâche sans échéance ne doit pas doubler celle qui en a une. Les mêler par date
    /// de création ferait remonter une note vieille de six mois au-dessus d'un rendez-vous
    /// de demain.
    func testUneTacheSansEcheancePasseApresCellesQuiEnOnt() {
        let demain = Date(timeIntervalSince1970: 1_788_100_000)
        let ordonnees = Taches.ordonner([
            tache("sans échéance"), tache("demain", echeance: demain),
        ])
        XCTAssertEqual(ordonnees.first?.echeance, demain)
        XCTAssertNil(ordonnees.last?.echeance)
    }

    /// Entre deux tâches sans échéance, la plus récente d'abord : c'est celle qu'on vient
    /// d'écrire, et qu'on cherche des yeux.
    func testEntreDeuxTachesSansEcheanceLaPlusRecenteRemonte() {
        let vieille = Date(timeIntervalSince1970: 1_780_000_000)
        let neuve = Date(timeIntervalSince1970: 1_788_000_000)
        let ordonnees = Taches.ordonner([
            tache("vieille", creee: vieille), tache("neuve", creee: neuve),
        ])
        XCTAssertEqual(ordonnees.first?.creee, neuve)
    }

    // ─── Le retard ───

    func testUneEcheanceDepasseeEstUnRetard() {
        let hier = Date(timeIntervalSince1970: 1_787_900_000)
        let maintenant = Date(timeIntervalSince1970: 1_788_000_000)
        XCTAssertTrue(tache("x", echeance: hier).enRetard(maintenant))
    }

    /// Une tâche faite n'est jamais en retard, même échue. L'afficher en rouge après coup
    /// reprocherait quelque chose qui vient d'être réglé.
    func testUneTacheFaiteNEstJamaisEnRetard() {
        let hier = Date(timeIntervalSince1970: 1_787_900_000)
        let maintenant = Date(timeIntervalSince1970: 1_788_000_000)
        XCTAssertFalse(tache("x", echeance: hier, faite: true).enRetard(maintenant))
        XCTAssertFalse(tache("sans échéance").enRetard(maintenant))
    }

    // ─── Le contenu scellé ───

    /// Les noms de champs sont le contrat avec le client web — `TaskContent` dans
    /// `frontend/src/lib/zk.ts`.
    func testLeContenuGardeLesNomsDeChampsDuWeb() throws {
        let json = try XCTUnwrap(
            try JSONSerialization.jsonObject(
                with: JSONEncoder().encode(ContenuDeTache(title: "Passeport", notes: "avant juin")))
                as? [String: Any])
        XCTAssertEqual(Set(json.keys), ["title", "notes"])
    }
}
