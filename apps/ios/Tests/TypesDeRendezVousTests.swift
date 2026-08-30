import XCTest

@testable import Ghostcal

/// Ce qui décide, pour les types de rendez-vous.
final class TypesDeRendezVousTests: XCTestCase {

    private func type(actif: Bool = true) throws -> TypeDeRendezVousDTO {
        let brut = Data(
            #"""
            {"id":"11111111-1111-1111-1111-111111111111","organization_slug":"stackops",
             "slug":"decouverte","title":"Découverte","description":"30 minutes",
             "duration_min":30,"slot_interval_min":15,"buffer_before_min":5,
             "buffer_after_min":10,"min_notice_min":120,"date_window_days":30,
             "max_per_day":4,"location_type":"google_meet","active":\#(actif),
             "questions":[{"id":"q1","label":"Sujet","type":"text","required":true,
                           "options":[]}],
             "kind":"solo","host_ids":["u1"],"capacity":1,
             "redirect_url":"https://exemple.test/merci"}
            """#.utf8)
        return try JSONDecoder().decode(TypeDeRendezVousDTO.self, from: brut)
    }

    // ─── La mise à jour ───

    /// La route est un `PUT` qui attend l'objet complet. N'envoyer que le champ modifié
    /// remettrait les autres à leur défaut : quelqu'un qui ferme un créneau depuis son
    /// téléphone perdrait ses tampons, son préavis et ses questions — sans erreur, et sans
    /// s'en apercevoir avant la prochaine réservation.
    func testBasculerNeChangeQueLActivite() throws {
        let avant = try type(actif: true)
        let apres = TypeDeRendezVousModifie(avant, actif: false)

        XCTAssertFalse(apres.active)
        XCTAssertEqual(apres.title, avant.title)
        XCTAssertEqual(apres.duration_min, 30)
        XCTAssertEqual(apres.slot_interval_min, 15)
        XCTAssertEqual(apres.buffer_before_min, 5)
        XCTAssertEqual(apres.buffer_after_min, 10)
        XCTAssertEqual(apres.min_notice_min, 120)
        XCTAssertEqual(apres.date_window_days, 30)
        XCTAssertEqual(apres.max_per_day, 4)
        XCTAssertEqual(apres.location_type, "google_meet")
        XCTAssertEqual(apres.questions.count, 1)
        XCTAssertEqual(apres.kind, "solo")
        XCTAssertEqual(apres.host_ids, ["u1"])
        XCTAssertEqual(apres.capacity, 1)
        XCTAssertEqual(apres.redirect_url, "https://exemple.test/merci")
    }

    /// Sans argument, rien ne change — la même structure sert aussi à réémettre tel quel.
    func testSansChangementLActiviteEstConservee() throws {
        XCTAssertTrue(TypeDeRendezVousModifie(try type(actif: true)).active)
        XCTAssertFalse(TypeDeRendezVousModifie(try type(actif: false)).active)
    }

    /// Les noms de champs partent au serveur : un renommage ici ferait perdre un réglage
    /// en silence, puisque le serveur remplacerait l'absent par son défaut.
    func testLObjetEnvoyeGardeLesNomsDuServeur() throws {
        let json = try XCTUnwrap(
            try JSONSerialization.jsonObject(
                with: JSONEncoder().encode(TypeDeRendezVousModifie(try type())))
                as? [String: Any])
        XCTAssertEqual(
            Set(json.keys),
            [
                "title", "duration_min", "slot_interval_min", "buffer_before_min",
                "buffer_after_min", "min_notice_min", "date_window_days", "max_per_day",
                "location_type", "active", "questions", "kind", "host_ids", "capacity",
                "redirect_url",
            ])
    }

    // ─── Le lien public ───

    /// Construit depuis l'adresse que l'utilisateur a saisie, jamais depuis une constante :
    /// chaque client a sa propre instance, et un lien vers le mauvais domaine ne mènerait
    /// nulle part — sans qu'aucune erreur ne le signale, puisque c'est le destinataire qui
    /// le découvrirait.
    func testLeLienPublicSuitLAdresseDuServeur() throws {
        let serveur = try XCTUnwrap(URL(string: "https://ghostcal.stackops.ch"))
        let lien = TypesDeRendezVous.lienPublic(try type(), serveur: serveur)
        XCTAssertEqual(lien?.absoluteString, "https://ghostcal.stackops.ch/stackops/decouverte")
    }

    func testLeLienPublicFonctionneAussiEnBoucleLocale() throws {
        let serveur = try XCTUnwrap(AdresseDeServeur.normaliser("localhost:5173"))
        let lien = TypesDeRendezVous.lienPublic(try type(), serveur: serveur)
        XCTAssertEqual(lien?.absoluteString, "http://localhost:5173/stackops/decouverte")
    }
}
