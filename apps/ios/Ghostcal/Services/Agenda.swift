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

/// Un calendrier de l'utilisateur.
///
/// `can_write` compte : un calendrier partagé par quelqu'un d'autre peut être en lecture
/// seule. Proposer d'y écrire ferait échouer l'enregistrement après que l'utilisateur a
/// tout saisi — le pire moment pour apprendre qu'on n'avait pas le droit.
struct CalendrierDTO: Decodable, Identifiable, Hashable {
    let id: UUID
    let name: String
    let color: String
    let is_default: Bool
    let is_shared: Bool
    let owner_name: String?
    let can_write: Bool?

    /// Absent d'un serveur antérieur au champ : on retombe alors sur « oui », qui était
    /// le comportement d'avant. Refuser par défaut priverait d'écriture sur un serveur
    /// parfaitement fonctionnel.
    var inscriptible: Bool { can_write ?? true }
}

/// Le détail d'un événement, tel que le serveur le rend.
struct EvenementDTO: Decodable {
    let id: UUID
    let calendar_id: UUID
    let start_at: Date
    let end_at: Date
    let timezone: String
    let all_day: Bool
    let content: String?
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
    /// L'identifiant de l'événement, quand la ligne en est un.
    ///
    /// Absent d'une occurrence de série développée par le serveur, et d'un créneau venu
    /// d'un calendrier externe : ces lignes-là s'affichent mais ne se modifient pas. Le
    /// bouton n'apparaît donc que lorsqu'il y a quelque chose à ouvrir.
    let evenement: UUID?
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

    func calendriers() async throws -> [CalendrierDTO] {
        try await api.obtenir("v1/me/calendars")
    }

    /// Crée un événement. Le contenu est scellé ici ; les heures partent en clair.
    ///
    /// Ce n'est pas une concession : sans les heures, le serveur ne saurait ni répondre
    /// « occupé » à un lien de disponibilité, ni envoyer un rappel. Il apprend qu'un
    /// créneau est pris, jamais par quoi.
    @discardableResult
    func creerUnEvenement(
        titre: String, description: String = "", lieu: String = "",
        debut: Date, fin: Date, journeeEntiere: Bool,
        calendrier: UUID, organisation: UUID
    ) async throws -> UUID {
        struct Corps: Encodable {
            let calendar_id: String
            let start_at: String
            let end_at: String
            let timezone: String
            let all_day: Bool
            let content: String
        }
        struct Cree: Decodable { let id: UUID }

        let clair = try JSONEncoder().encode(
            ContenuDEvenement(title: titre, description: description, location: lieu))
        let scelle = try await auth.sceller(clair, organisation: organisation.uuidString)
        let formateur = ISO8601DateFormatter()
        formateur.formatOptions = [.withInternetDateTime]
        let reponse: Cree = try await api.envoyer(
            "POST", "v1/me/calendar/events",
            Corps(
                calendar_id: calendrier.uuidString,
                start_at: formateur.string(from: debut), end_at: formateur.string(from: fin),
                // Le fuseau de l'appareil : c'est celui dans lequel l'utilisateur a lu les
                // heures qu'il vient de choisir. En envoyer un autre décalerait ce qu'il a
                // sous les yeux.
                timezone: TimeZone.current.identifier,
                all_day: journeeEntiere, content: scelle))
        return reponse.id
    }

    /// Le détail d'un événement, contenu ouvert.
    ///
    /// L'agenda n'en donne que ce qu'il faut pour l'afficher ; modifier demande le reste —
    /// le calendrier auquel il appartient, la description, le fuseau dans lequel il a été
    /// posé.
    func evenement(_ id: UUID, organisation: UUID) async throws -> (
        detail: EvenementDTO, contenu: ContenuDEvenement?
    ) {
        let brut: EvenementDTO = try await api.obtenir("v1/me/calendar/events/\(id.uuidString)")
        var contenu: ContenuDEvenement?
        if let scelle = brut.content,
            let clair = await auth.ouvrir(scelle, organisation: organisation.uuidString)
        {
            contenu = try? JSONDecoder().decode(ContenuDEvenement.self, from: clair)
        }
        return (brut, contenu)
    }

    /// Modifie un événement. Comme à la création, le contenu est scellé vers la clé
    /// **courante** : un événement corrigé après une rotation redevient lisible par tous,
    /// ce qui est précisément l'effet recherché.
    func modifierUnEvenement(
        _ id: UUID, titre: String, description: String, lieu: String,
        debut: Date, fin: Date, journeeEntiere: Bool, fuseau: String,
        calendrier: UUID, organisation: UUID
    ) async throws {
        struct Corps: Encodable {
            let calendar_id: String
            let start_at: String
            let end_at: String
            let timezone: String
            let all_day: Bool
            let content: String
        }
        let clair = try JSONEncoder().encode(
            ContenuDEvenement(title: titre, description: description, location: lieu))
        let scelle = try await auth.sceller(clair, organisation: organisation.uuidString)
        let formateur = ISO8601DateFormatter()
        formateur.formatOptions = [.withInternetDateTime]
        try await api.envoyerSansReponse(
            "PUT", "v1/me/calendar/events/\(id.uuidString)",
            Corps(
                calendar_id: calendrier.uuidString,
                start_at: formateur.string(from: debut), end_at: formateur.string(from: fin),
                timezone: fuseau, all_day: journeeEntiere, content: scelle))
    }

    func supprimerUnEvenement(_ id: UUID) async throws {
        struct Rien: Encodable {}
        try await api.envoyerSansReponse(
            "DELETE", "v1/me/calendar/events/\(id.uuidString)", Rien())
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
                    evenement: brute.read_only ? nil : brute.event_id,
                    debut: brute.start, fin: brute.end, journeeEntiere: brute.all_day,
                    lectureSeule: brute.read_only, titre: titre, lieu: lieu, source: brute.source))
        }
        return resultat.sorted { $0.debut < $1.debut }
    }
}
