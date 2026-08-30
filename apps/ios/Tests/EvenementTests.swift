import XCTest

@testable import Ghostcal

/// Ce qui décide, à la création d'un rendez-vous.
final class EvenementTests: XCTestCase {

    // ─── L'heure proposée ───

    /// On ne prend pas rendez-vous à 14 h 37. Proposer « maintenant » obligerait à
    /// corriger les minutes à chaque création.
    func testLHeureProposeeEstLaProchaineDemiHeure() {
        let calendrier = Calendar.current
        for (minute, attendue) in [(0, 30), (1, 30), (29, 30), (30, 0), (31, 0), (59, 0)] {
            let depart = calendrier.date(
                from: DateComponents(year: 2026, month: 9, day: 1, hour: 14, minute: minute))!
            let proposee = Date.prochaineDemiHeure(depart)
            XCTAssertEqual(
                calendrier.component(.minute, from: proposee), attendue,
                "à 14 h \(minute), on propose \(attendue)")
            XCTAssertGreaterThan(proposee, depart, "l'heure proposée est toujours devant")
        }
    }

    func testLHeureProposeeNAJamaisDeSecondes() {
        let calendrier = Calendar.current
        let depart = calendrier.date(
            from: DateComponents(
                year: 2026, month: 9, day: 1, hour: 14, minute: 12, second: 47))!
        XCTAssertEqual(calendrier.component(.second, from: Date.prochaineDemiHeure(depart)), 0)
    }

    // ─── Les calendriers ───

    /// Un calendrier partagé peut être en lecture seule. Le proposer ferait échouer
    /// l'enregistrement une fois tout saisi — le pire moment pour apprendre qu'on n'avait
    /// pas le droit d'écrire.
    func testUnCalendrierEnLectureSeuleNEstPasInscriptible() throws {
        let brut = Data(
            #"""
            [{"id":"11111111-1111-1111-1111-111111111111","name":"Partagé","color":"#fff",
              "is_default":false,"is_shared":true,"owner_name":"Kevin","can_write":false}]
            """#.utf8)
        let calendriers = try JSONDecoder().decode([CalendrierDTO].self, from: brut)
        XCTAssertFalse(try XCTUnwrap(calendriers.first).inscriptible)
    }

    /// Le champ manque sur un serveur antérieur. Refuser par défaut priverait d'écriture
    /// sur une instance parfaitement fonctionnelle : on retombe sur le comportement
    /// d'avant, qui était d'autoriser.
    func testUnCalendrierSansLeChampResteInscriptible() throws {
        let brut = Data(
            #"""
            [{"id":"11111111-1111-1111-1111-111111111111","name":"Perso","color":"#fff",
              "is_default":true,"is_shared":false,"owner_name":null}]
            """#.utf8)
        let calendriers = try JSONDecoder().decode([CalendrierDTO].self, from: brut)
        XCTAssertTrue(try XCTUnwrap(calendriers.first).inscriptible)
    }

    // ─── La journée entière ───

    /// Une journée entière couvre le jour civil complet. Envoyer l'instant choisi tel quel
    /// ferait durer l'événement de 14 h 30 à 14 h 30 — le serveur l'accepterait sans
    /// broncher, et l'agenda afficherait une journée de durée nulle.
    func testUneJourneeEntiereCouvreLeJourEntier() {
        let calendrier = Calendar.current
        let choisi = calendrier.date(
            from: DateComponents(year: 2026, month: 9, day: 1, hour: 14, minute: 30))!
        let debut = calendrier.startOfDay(for: choisi)
        let fin = calendrier.date(byAdding: .day, value: 1, to: debut)!

        XCTAssertEqual(calendrier.component(.hour, from: debut), 0)
        XCTAssertEqual(fin.timeIntervalSince(debut), 24 * 3600, accuracy: 3600)
        XCTAssertGreaterThan(fin, debut, "une journée entière n'est jamais de durée nulle")
    }
}
