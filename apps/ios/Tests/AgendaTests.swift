import XCTest

@testable import Ghostcal

/// Ce qui décide, dans l'agenda.
///
/// Le regroupement par journée et la lecture du contenu scellé : deux endroits où une
/// erreur ne se voit pas à la compilation, et se remarque en production sous la forme
/// d'un rendez-vous rangé au mauvais jour ou d'une ligne disparue.
final class AgendaTests: XCTestCase {

    private func ligne(
        _ debut: Date, titre: LigneDAgenda.Titre = .dechiffre("x")
    ) -> LigneDAgenda {
        LigneDAgenda(
            id: UUID().uuidString, evenement: UUID(), debut: debut,
            fin: debut.addingTimeInterval(3600),
            journeeEntiere: false, lectureSeule: false, titre: titre, lieu: nil,
            source: "event")
    }

    // ─── Le regroupement ───

    func testLesLignesSeRangentParJourEtDansLOrdre() {
        let calendrier = Calendar.current
        let matin = calendrier.date(from: DateComponents(year: 2026, month: 9, day: 1, hour: 9))!
        let soir = calendrier.date(from: DateComponents(year: 2026, month: 9, day: 1, hour: 18))!
        let lendemain = calendrier.date(
            from: DateComponents(year: 2026, month: 9, day: 2, hour: 8))!

        let jours = ModeleDAgenda.parJour([ligne(soir), ligne(lendemain), ligne(matin)])
        XCTAssertEqual(jours.count, 2)
        XCTAssertEqual(jours[0].lignes.count, 2)
        XCTAssertEqual(jours[0].lignes.first?.debut, matin, "le matin passe avant le soir")
        XCTAssertEqual(jours[1].lignes.count, 1)
        XCTAssertLessThan(jours[0].id, jours[1].id, "les jours se suivent")
    }

    /// Le serveur date en UTC. Grouper sur ces dates brutes rangerait un rendez-vous de
    /// 23 h 30 au lendemain pour qui vit à l'est de Greenwich — le regroupement doit se
    /// faire dans le fuseau de l'appareil.
    func testLeRegroupementSuitLeFuseauDeLAppareil() {
        let calendrier = Calendar.current
        let tard = calendrier.date(
            from: DateComponents(year: 2026, month: 9, day: 1, hour: 23, minute: 30))!
        let jours = ModeleDAgenda.parJour([ligne(tard)])
        XCTAssertEqual(jours.count, 1)
        XCTAssertEqual(
            calendrier.component(.day, from: jours[0].id), 1,
            "un rendez-vous de 23 h 30 appartient au jour où on le vit")
    }

    func testUnAgendaVideNeProduitAucunJour() {
        XCTAssertTrue(ModeleDAgenda.parJour([]).isEmpty)
    }

    // ─── Les quatre sortes de titres ───

    /// Elles doivent rester distinctes. Confondre « illisible » et « sans titre » ferait
    /// passer une clé manquante pour un événement mal rempli ; confondre « déchiffré » et
    /// « en clair » laisserait croire qu'un titre chiffré a fuité au serveur.
    func testLesQuatreTitresSeDistinguent() {
        let titres: [LigneDAgenda.Titre] = [
            .dechiffre("Dentiste"), .enClair("Dentiste"), .illisible, .sansTitre,
        ]
        XCTAssertEqual(Set(titres).count, 4)
    }

    // ─── Le contenu scellé ───

    /// Les noms de champs sont le contrat avec le client web : un champ renommé d'un côté
    /// ne casse aucune compilation, il rend les événements illisibles chez l'autre.
    func testLeContenuGardeLesNomsDeChampsDuWeb() throws {
        let contenu = ContenuDEvenement(
            title: "Dentiste", description: "contrôle annuel", location: "Genève")
        let json = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: JSONEncoder().encode(contenu))
                as? [String: Any])
        XCTAssertEqual(Set(json.keys), ["title", "description", "location"])
    }

    /// Un contenu écrit par une version plus ancienne peut manquer un champ. Le refuser
    /// entièrement ferait disparaître l'événement ; l'accepter à moitié vaut mieux.
    func testUnContenuIncompletEstRefuseSansFaireDisparaitreLaLigne() {
        let brut = Data(#"{"title":"Dentiste"}"#.utf8)
        XCTAssertNil(
            try? JSONDecoder().decode(ContenuDEvenement.self, from: brut),
            "le décodage échoue — et l'agenda affiche alors « chiffré », pas rien")
    }
}
