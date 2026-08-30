import Foundation

/// Une organisation dont on est membre.
struct OrganisationDTO: Decodable, Identifiable, Hashable {
    let id: UUID
    let name: String
    let slug: String
    let role: String
}

/// Une ligne d'agenda, telle que le serveur la rend.
///
/// Le serveur ne sait pas ce qu'elle contient : `content` est scellé vers la clé publique
/// de l'organisation. Il connaît en revanche **quand** — début, fin, journée entière — et
/// c'est délibéré : sans les heures en clair, il ne pourrait ni répondre « occupé » à un
/// lien de disponibilité, ni envoyer un rappel.
///
/// `title` existe et n'est **pas** le titre chiffré : il porte les libellés qui sont
/// publics par nature — une réservation prise depuis un lien, un calendrier externe
/// abonné. Les confondre afficherait « (chiffré) » là où le serveur a légitimement un
/// texte, ou pire, laisserait croire qu'un titre chiffré a fuité.
struct LigneDAgendaDTO: Decodable {
    let source: String
    let start: Date
    let end: Date
    let all_day: Bool
    let calendar_id: UUID?
    let event_id: UUID?
    let content: String?
    let title: String?
    let read_only: Bool
    let reminder_minutes: Int?
}

/// Ce que contient un événement, une fois ouvert.
///
/// Même forme que le client web, au champ près — `frontend/src/lib/zk.ts`, `EventContent`.
/// Le blob est un JSON scellé ; un champ renommé d'un côté ne casse aucune compilation, il
/// rend simplement les événements illisibles chez l'autre.
struct ContenuDEvenement: Codable, Equatable {
    var title: String
    var description: String
    var location: String
}

/// Une ligne d'agenda, contenu ouvert quand on a pu.
struct LigneDAgenda: Identifiable, Hashable {
    let id: String
    let debut: Date
    let fin: Date
    let journeeEntiere: Bool
    let lectureSeule: Bool
    /// Le titre à afficher, et d'où il vient. La distinction se voit à l'écran : un
    /// événement qu'on n'a pas su ouvrir ne doit pas se confondre avec un événement sans
    /// titre, ni disparaître.
    let titre: Titre
    let lieu: String?
    let source: String

    enum Titre: Hashable {
        /// Ouvert avec la clé de l'organisation.
        case dechiffre(String)
        /// Rendu en clair par le serveur — réservation, calendrier externe.
        case enClair(String)
        /// Scellé, et la clé n'a pas ouvert. Un trou visible vaut mieux qu'une ligne
        /// absente : l'heure est occupée, l'utilisateur doit le voir.
        case illisible
        case sansTitre
    }
}

/// Lit l'agenda et ouvre ce qui peut l'être.
actor Agenda {
    private let api: APIClient
    private let auth: Auth

    init(api: APIClient, auth: Auth) {
        self.api = api
        self.auth = auth
    }

    func organisations() async throws -> [OrganisationDTO] {
        try await api.obtenir("v1/me/organizations")
    }

    /// L'agenda entre deux dates.
    ///
    /// La fenêtre est bornée par le serveur à 366 jours — un événement récurrent développé
    /// sur une plage illimitée serait un déni de service. On demande donc une fenêtre
    /// étroite, et on la déplace, plutôt que de tout charger.
    func lignes(de debut: Date, a fin: Date, organisation: UUID) async throws -> [LigneDAgenda] {
        let formateur = ISO8601DateFormatter()
        formateur.formatOptions = [.withInternetDateTime]
        let brutes: [LigneDAgendaDTO] = try await api.obtenir(
            "v1/me/calendar/agenda",
            ["from": formateur.string(from: debut), "to": formateur.string(from: fin)])

        var resultat: [LigneDAgenda] = []
        for brute in brutes {
            var titre = LigneDAgenda.Titre.sansTitre
            var lieu: String?

            if let scelle = brute.content {
                if let clair = await auth.ouvrir(scelle, organisation: organisation.uuidString),
                    let contenu = try? JSONDecoder().decode(ContenuDEvenement.self, from: clair)
                {
                    titre = .dechiffre(contenu.title)
                    lieu = contenu.location.isEmpty ? nil : contenu.location
                } else {
                    titre = .illisible
                }
            } else if let enClair = brute.title, !enClair.isEmpty {
                titre = .enClair(enClair)
            }

            resultat.append(
                LigneDAgenda(
                    // Une ligne d'agenda n'a pas toujours d'identifiant d'événement : une
                    // occurrence de série ou un créneau externe n'en portent pas. La date
                    // de début complète la clé, sinon `ForEach` afficherait la première et
                    // tairait les suivantes.
                    id:
                        "\(brute.event_id?.uuidString ?? brute.source)-\(brute.start.timeIntervalSince1970)",
                    debut: brute.start, fin: brute.end, journeeEntiere: brute.all_day,
                    lectureSeule: brute.read_only, titre: titre, lieu: lieu, source: brute.source))
        }
        return resultat.sorted { $0.debut < $1.debut }
    }
}
