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
