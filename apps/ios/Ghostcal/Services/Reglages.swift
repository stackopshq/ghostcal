import Foundation

// MARK: - Disponibilités

/// Une plage récurrente : « lundi de 9 h à 12 h ».
///
/// `weekday` suit la convention du serveur — 0 = lundi. `Calendar` d'Apple compte
/// autrement (1 = dimanche), et confondre les deux décalerait tout l'horaire d'un jour,
/// silencieusement : l'écran afficherait un horaire cohérent, mais pas celui qui gouverne
/// les réservations.
struct RegleDTO: Codable, Hashable {
    let weekday: Int
    let start: String
    let end: String

    /// Le nom du jour, dans la langue de l'appareil.
    ///
    /// La valeur est vérifiée **avant** la conversion, et non après : le modulo ramènerait
    /// n'importe quel entier dans les clous, si bien qu'un `weekday` de 42 s'afficherait
    /// « lundi » — une valeur fausse, présentée avec l'assurance d'une vraie. Un point
    /// d'interrogation se remarque ; un mauvais jour, non.
    var jour: String {
        guard (0...6).contains(weekday) else { return "?" }
        let symboles = Calendar.current.standaloneWeekdaySymbols
        // De la convention serveur (0 = lundi) vers l'index d'Apple (0 = dimanche).
        let index = (weekday + 1) % 7
        return symboles.indices.contains(index) ? symboles[index] : "?"
    }
}

/// Une exception à l'horaire : un jour fermé, ou ouvert autrement.
struct ExceptionDTO: Codable, Hashable {
    let day: String
    let is_available: Bool
    let start: String?
    let end: String?
}

/// Un horaire de disponibilité.
struct HoraireDTO: Decodable, Identifiable, Hashable {
    let id: UUID
    let name: String
    let timezone: String
    let rules: [RegleDTO]
    let overrides: [ExceptionDTO]
}

// MARK: - Sondages

/// Un sondage, vu de la liste.
struct SondageDTO: Decodable, Identifiable, Hashable {
    let id: UUID
    let slug: String
    let title: String
    let status: String
    let option_count: Int
    let vote_count: Int
}

/// Un créneau proposé dans un sondage.
struct OptionDeSondageDTO: Decodable, Identifiable, Hashable {
    let id: String
    let start_at: Date
    let end_at: Date
    let votes: Int
}

/// Qui a voté, et pour quoi.
struct VotantDTO: Decodable, Hashable {
    let name: String
    let email: String
    let option_ids: [String]
}

/// Un sondage au complet.
struct SondageDetailDTO: Decodable {
    let id: UUID
    let slug: String
    let title: String
    let duration_min: Int
    let status: String
    let owner_name: String
    let finalized_option_id: String?
    let options: [OptionDeSondageDTO]
    let voters: [VotantDTO]
}

// MARK: - Profil

struct ProfilDTO: Codable, Equatable {
    let id: String
    let email: String
    let name: String
    let timezone: String
    let email_verified: Bool
    let avatar_url: String?
}

// MARK: - Équipe

struct MembreDTO: Decodable, Identifiable, Hashable {
    let user_id: String
    let name: String
    let email: String
    let role: String
    let joined_at: Date

    var id: String { user_id }

    /// Le rôle, dit en français. Un rôle inconnu s'affiche tel quel plutôt que d'être
    /// masqué : un serveur plus récent peut en introduire, et taire celui d'un membre
    /// serait pire que l'afficher en anglais.
    var role_lisible: String {
        switch role {
        case "owner": return String(localized: "Propriétaire")
        case "admin": return String(localized: "Administrateur")
        case "member": return String(localized: "Membre")
        default: return role
        }
    }
}

/// Les écrans de réglage : disponibilités, sondages, profil, équipe.
///
/// Un seul service pour quatre lectures qui n'ont rien de commun sinon d'être des
/// réglages. Les séparer en quatre acteurs aurait multiplié la cérémonie sans rien
/// clarifier : aucun ne porte d'état, tous ne font qu'un appel.
actor Reglages {
    private let api: APIClient

    init(api: APIClient) { self.api = api }

    func horaires() async throws -> [HoraireDTO] {
        try await api.obtenir("v1/me/schedules")
    }

    func sondages() async throws -> [SondageDTO] {
        try await api.obtenir("v1/me/polls")
    }

    func sondage(_ id: UUID) async throws -> SondageDetailDTO {
        try await api.obtenir("v1/me/polls/\(id.uuidString)")
    }

    /// Retient un créneau : le sondage se ferme et l'événement se crée côté serveur.
    @discardableResult
    func finaliser(_ id: UUID, option: String) async throws -> SondageDetailDTO {
        struct Corps: Encodable { let option_id: String }
        return try await api.envoyer(
            "POST", "v1/me/polls/\(id.uuidString)/finalize", Corps(option_id: option))
    }

    func annulerLeSondage(_ id: UUID) async throws {
        struct Rien: Encodable {}
        try await api.envoyerSansReponse("DELETE", "v1/me/polls/\(id.uuidString)", Rien())
    }

    /// Change le rôle d'un membre. Le serveur rend la liste à jour, qu'on réutilise plutôt
    /// que de relire : deux appels donneraient deux vérités possibles entre-temps.
    @discardableResult
    func changerLeRole(_ utilisateur: String, role: String) async throws -> [MembreDTO] {
        struct Corps: Encodable { let role: String }
        return try await api.envoyer(
            "PATCH", "v1/me/organization/members/\(utilisateur)", Corps(role: role))
    }

    func retirerLeMembre(_ utilisateur: String) async throws {
        struct Rien: Encodable {}
        try await api.envoyerSansReponse(
            "DELETE", "v1/me/organization/members/\(utilisateur)", Rien())
    }

    func profil() async throws -> ProfilDTO {
        try await api.obtenir("v1/me/profile")
    }

    /// Le serveur attend les trois champs modifiables. `email` n'en fait pas partie : le
    /// changer demande une vérification, et cette route ne la déclenche pas.
    func enregistrerLeProfil(nom: String, fuseau: String, avatar: String?) async throws -> ProfilDTO
    {
        try await api.envoyer(
            "PUT", "v1/me/profile",
            CorpsDeProfil(name: nom, timezone: fuseau, avatar_url: avatar))
    }

    /// Ce qu'on envoie pour modifier un profil.
    ///
    /// L'encodage est explicite parce que le défaut de Swift ne convient pas ici : un
    /// optionnel nul est **omis** du JSON, alors que la route est un `PUT` qui remplace
    /// l'objet. Omettre `avatar_url` demande « ne touche pas » ; l'envoyer à `null`
    /// demande « efface ». L'écran qui retire une photo exprime la seconde.
    struct CorpsDeProfil: Encodable {
        let name: String
        let timezone: String
        let avatar_url: String?

        func encode(to encodeur: Encoder) throws {
            var conteneur = encodeur.container(keyedBy: Cles.self)
            try conteneur.encode(name, forKey: .name)
            try conteneur.encode(timezone, forKey: .timezone)
            try conteneur.encode(avatar_url, forKey: .avatar_url)
        }

        enum Cles: String, CodingKey {
            case name, timezone, avatar_url
        }
    }

    func membres() async throws -> [MembreDTO] {
        try await api.obtenir("v1/me/organization/members")
    }
}
