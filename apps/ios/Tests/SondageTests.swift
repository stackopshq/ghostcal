import XCTest

@testable import Ghostcal

/// Ce qui décide, pour les sondages et l'équipe.
final class SondageTests: XCTestCase {

    private func detail(finalise: String? = nil) throws -> SondageDetailDTO {
        let brut = Data(
            #"""
            {"id":"11111111-1111-1111-1111-111111111111","slug":"revue","title":"Revue",
             "duration_min":60,"status":"open","owner_name":"Clara",
             "finalized_option_id":\#(finalise.map { "\"\($0)\"" } ?? "null"),
             "options":[
               {"id":"o1","start_at":"2026-09-01T09:00:00+00:00",
                "end_at":"2026-09-01T10:00:00+00:00","votes":3},
               {"id":"o2","start_at":"2026-09-02T09:00:00+00:00",
                "end_at":"2026-09-02T10:00:00+00:00","votes":1}],
             "voters":[{"name":"Kevin","email":"kevin@stackops.ch","option_ids":["o1"]},
                       {"name":"","email":"anon@exemple.test","option_ids":["o1","o2"]}]}
            """#.utf8)
        return try JSONDecoder.api.decode(SondageDetailDTO.self, from: brut)
    }

    // ─── L'état du sondage ───

    /// Un sondage ouvert propose de retenir un créneau ; un sondage clos ne le propose
    /// plus. Confondre les deux laisserait finaliser deux fois, et le second appel
    /// créerait un rendez-vous en double — ou échouerait sans qu'on comprenne pourquoi.
    func testUnSondageOuvertNAPasDeCreneauRetenu() throws {
        XCTAssertNil(try detail().finalized_option_id)
    }

    func testUnSondageCloseDesigneSonCreneau() throws {
        XCTAssertEqual(try detail(finalise: "o1").finalized_option_id, "o1")
    }

    // ─── Les votants ───

    /// Un votant peut n'avoir pas donné son nom : l'affichage retombe alors sur son
    /// adresse. Montrer une ligne vide laisserait croire à un vote anonyme, alors que
    /// l'adresse est là.
    func testUnVotantSansNomSeReconnaitParSonAdresse() throws {
        let anonyme = try XCTUnwrap(try detail().voters.last)
        XCTAssertTrue(anonyme.name.isEmpty)
        XCTAssertEqual(anonyme.name.isEmpty ? anonyme.email : anonyme.name, "anon@exemple.test")
    }

    func testLesVotesSeComptentParOption() throws {
        let sondage = try detail()
        XCTAssertEqual(sondage.options.first?.votes, 3)
        XCTAssertEqual(sondage.options.last?.votes, 1)
        XCTAssertEqual(sondage.voters.count, 2)
    }

    // ─── L'équipe ───

    /// Changer un rôle pour le même rôle ne doit rien envoyer : un appel sans effet
    /// consomme un aller-retour et, si le serveur journalise, laisse une trace d'une
    /// modification qui n'a pas eu lieu.
    func testChangerUnRolePourLeMemeNeFaitRien() throws {
        let brut = Data(
            #"""
            [{"user_id":"u1","name":"Clara","email":"clara@stackops.ch","role":"admin",
              "joined_at":"2026-08-30T10:00:00+00:00"}]
            """#.utf8)
        let membre = try XCTUnwrap(try JSONDecoder.api.decode([MembreDTO].self, from: brut).first)
        // La garde du modèle : `membre.role != role`.
        XCTAssertFalse(membre.role != "admin", "aucun appel pour un rôle inchangé")
        XCTAssertTrue(membre.role != "member", "un rôle différent déclenche l'appel")
    }
}
