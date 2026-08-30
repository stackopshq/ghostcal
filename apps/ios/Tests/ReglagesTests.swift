import XCTest

@testable import Ghostcal

/// Ce qui décide, dans les réglages.
final class ReglagesTests: XCTestCase {

    // ─── Le jour de la semaine ───

    /// **Deux conventions se croisent ici.** Le serveur compte 0 = lundi ; `Calendar`
    /// d'Apple compte 1 = dimanche. Les confondre décalerait tout l'horaire d'un jour, et
    /// l'écran resterait cohérent — il afficherait simplement un autre horaire que celui
    /// qui gouverne réellement les réservations. Personne ne le remarquerait avant qu'un
    /// invité réserve un dimanche.
    func testLesJoursSuiventLaConventionDuServeur() {
        let symboles = Calendar.current.standaloneWeekdaySymbols
        // 0 = lundi côté serveur → index 1 chez Apple.
        XCTAssertEqual(RegleDTO(weekday: 0, start: "09:00", end: "12:00").jour, symboles[1])
        // 6 = dimanche côté serveur → index 0 chez Apple.
        XCTAssertEqual(RegleDTO(weekday: 6, start: "09:00", end: "12:00").jour, symboles[0])
    }

    /// Un jour hors bornes ne doit pas faire tomber l'écran : mieux vaut un horaire avec un
    /// point d'interrogation qu'une liste de disponibilités qui refuse de s'afficher.
    func testUnJourHorsBornesNeFaitPasTomberLEcran() {
        XCTAssertEqual(RegleDTO(weekday: 42, start: "09:00", end: "12:00").jour, "?")
    }

    // ─── Les rôles ───

    /// Un rôle inconnu s'affiche tel quel plutôt que d'être masqué : un serveur plus
    /// récent peut en introduire, et taire celui d'un membre serait pire que l'afficher
    /// en anglais.
    func testUnRoleInconnuSAfficheTelQuel() throws {
        let brut = Data(
            #"""
            [{"user_id":"u1","name":"Clara","email":"clara@stackops.ch","role":"guest_auditor",
              "joined_at":"2026-08-30T10:00:00+00:00"}]
            """#.utf8)
        let membres = try JSONDecoder.api.decode([MembreDTO].self, from: brut)
        XCTAssertEqual(try XCTUnwrap(membres.first).role_lisible, "guest_auditor")
    }

    func testLesRolesConnusSontTraduits() throws {
        for (brut, attendu) in [
            ("owner", "Propriétaire"), ("admin", "Administrateur"), ("member", "Membre"),
        ] {
            let json = Data(
                #"""
                [{"user_id":"u1","name":"x","email":"x@y.z","role":"\#(brut)",
                  "joined_at":"2026-08-30T10:00:00+00:00"}]
                """#.utf8)
            let membres = try JSONDecoder.api.decode([MembreDTO].self, from: json)
            XCTAssertEqual(try XCTUnwrap(membres.first).role_lisible, attendu)
        }
    }

    // ─── Le profil ───

    /// Le serveur attend exactement trois champs modifiables. `email` n'en fait pas partie :
    /// le changer demande une vérification que cette route ne déclenche pas, et l'envoyer
    /// ici le ferait silencieusement ignorer — ou pire, accepter sans vérification.
    func testLeProfilEnvoyeNeContientQueCeQuiSeModifie() throws {
        let json = try XCTUnwrap(
            try JSONSerialization.jsonObject(
                with: JSONEncoder().encode(
                    Reglages.CorpsDeProfil(
                        name: "Clara", timezone: "Europe/Zurich", avatar_url: nil)))
                as? [String: Any])
        XCTAssertEqual(Set(json.keys), ["name", "timezone", "avatar_url"])
        XCTAssertTrue(
            json["avatar_url"] is NSNull,
            "un avatar retiré part à `null` — l'omettre demanderait de ne pas y toucher")
    }
}
