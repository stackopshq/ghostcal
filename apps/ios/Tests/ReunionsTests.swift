import XCTest

@testable import Ghostcal

/// Ce qui décide, dans les réunions.
///
/// Le partage entre clair et scellé y est plus subtil qu'ailleurs : le titre du type de
/// rendez-vous et l'adresse e-mail sont publics par nature, le nom de l'invité ne l'est
/// pas toujours. Se tromper d'un côté afficherait « sans nom » là où le nom existe,
/// chiffré, juste à côté.
final class ReunionsTests: XCTestCase {

    // ─── Le nom de l'invité ───

    /// Quatre provenances distinctes, qui ne doivent pas se confondre : un nom en clair,
    /// un nom déchiffré, un nom scellé qu'on n'ouvre pas, et pas de nom du tout.
    func testLesQuatreProvenancesDuNomSeDistinguent() {
        let noms: [Reunion.NomDInvite] = [
            .enClair("Clara"), .dechiffre("Clara"), .illisible, .inconnu,
        ]
        XCTAssertEqual(Set(noms).count, 4)
    }

    // ─── Le contenu scellé ───

    /// Les noms de champs sont le contrat avec le client web — `InviteePrivate` dans
    /// `frontend/src/lib/zk.ts`.
    func testLeContenuGardeLesNomsDeChampsDuWeb() throws {
        let contenu = ContenuDInvite(
            name: "Clara", answers: ["Sujet": "Devis"], notes: "rappeler le budget")
        let json = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: JSONEncoder().encode(contenu))
                as? [String: Any])
        XCTAssertEqual(Set(json.keys), ["name", "answers", "notes"])
    }

    /// Les réponses arrivent dans un dictionnaire, qui n'a pas d'ordre. Les afficher tels
    /// quels ferait changer l'ordre à chaque lecture, et donnerait l'impression que le
    /// contenu bouge tout seul.
    func testLesReponsesSeTrientParQuestion() throws {
        let brut = Data(
            #"{"name":"Clara","answers":{"Zèbre":"z","Alpha":"a","Miel":"m"},"notes":""}"#.utf8)
        let contenu = try JSONDecoder().decode(ContenuDInvite.self, from: brut)
        let triees = contenu.answers.sorted { $0.key < $1.key }.map(\.key)
        XCTAssertEqual(triees, ["Alpha", "Miel", "Zèbre"])
    }

    // ─── Ce qui arrive quand un champ cesse d'être en clair ───

    /// Une décision prise pour la suite (ADR-0038) prévoit un mode où l'identité de
    /// l'invité est scellée : l'adresse cesserait d'être en clair. Avec un champ
    /// obligatoire, le décodage de **toute la liste** échouerait, et l'écran des réunions
    /// deviendrait vide sans rapport apparent avec la cause.
    ///
    /// Le test ne vérifie pas une fonctionnalité future : il vérifie qu'un client ne perd
    /// pas un écran entier parce qu'un champ est devenu facultatif.
    func testUneReunionSansAdresseSeDecodeQuandMeme() throws {
        let brut = Data(
            #"""
            [{"id":"11111111-1111-1111-1111-111111111111","event_title":"Découverte",
              "invitee_name":null,"invitee_email":null,"invitee_timezone":"Europe/Zurich",
              "start_at":"2026-09-01T09:00:00+00:00","end_at":"2026-09-01T10:00:00+00:00",
              "status":"confirmed","location":null,"meeting_url":null,
              "invitee_private":"scellé"}]
            """#.utf8)
        let reunions = try JSONDecoder.api.decode([ReunionDTO].self, from: brut)
        XCTAssertEqual(reunions.count, 1, "la liste se décode malgré l'adresse absente")
        XCTAssertNil(try XCTUnwrap(reunions.first).invitee_email)
    }

    func testUneReunionAvecAdresseSeDecodeCommeAvant() throws {
        let brut = Data(
            #"""
            [{"id":"11111111-1111-1111-1111-111111111111","event_title":"Découverte",
              "invitee_name":"Clara","invitee_email":"clara@stackops.ch",
              "invitee_timezone":"Europe/Zurich",
              "start_at":"2026-09-01T09:00:00+00:00","end_at":"2026-09-01T10:00:00+00:00",
              "status":"confirmed","location":null,"meeting_url":null,
              "invitee_private":null}]
            """#.utf8)
        let reunion = try XCTUnwrap(
            try JSONDecoder.api.decode([ReunionDTO].self, from: brut).first)
        XCTAssertEqual(reunion.invitee_email, "clara@stackops.ch")
    }

    // ─── Le statut ───

    /// Un statut inconnu du serveur ne doit pas faire échouer la lecture de la liste : une
    /// réunion qu'on n'affiche pas est pire qu'une réunion au statut imprécis.
    func testUnStatutInconnuNeFaitPasEchouerLaLecture() {
        XCTAssertEqual(Reunion.Statut("confirmed"), .confirmee)
        XCTAssertEqual(Reunion.Statut("cancelled"), .annulee)
        XCTAssertEqual(Reunion.Statut("rescheduled_pending"), .autre)
        XCTAssertEqual(Reunion.Statut(""), .autre)
    }

    // ─── La portée ───

    /// Le serveur tranche entre à venir et passées : demander les deux et filtrer ici
    /// obligerait à télécharger un historique entier pour afficher trois lignes.
    func testLesPorteesOntLesValeursDuServeur() {
        XCTAssertEqual(Reunions.Portee.aVenir.rawValue, "upcoming")
        XCTAssertEqual(Reunions.Portee.passees.rawValue, "past")
    }
}
