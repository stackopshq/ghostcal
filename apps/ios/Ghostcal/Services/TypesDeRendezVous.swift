import Foundation

/// Une question posée au visiteur au moment de réserver.
struct QuestionDTO: Codable, Identifiable, Hashable {
    let id: String
    let label: String
    let type: String
    let required: Bool
    let options: [String]
}

/// Un type de rendez-vous : ce qu'on propose à réserver.
///
/// Rien n'est chiffré ici, et c'est voulu — cette page est **publique**. Le titre, la
/// durée et les questions sont lus par des inconnus qui n'ont aucune clé ; les sceller
/// rendrait la réservation impossible. Ce qui est scellé, ce sont les réponses de
/// l'invité, une fois qu'il a réservé.
/// Tous les champs sont décodés, y compris ceux que l'écran n'affiche pas.
///
/// La route de mise à jour est un `PUT` et attend l'objet **complet** : n'envoyer que le
/// champ modifié remettrait les autres à leur valeur par défaut. Un utilisateur qui coupe
/// un créneau depuis son téléphone perdrait ses tampons, son préavis et ses questions
/// sans qu'aucune erreur ne le signale — il ne s'en apercevrait qu'à la prochaine
/// réservation, ou jamais.
struct TypeDeRendezVousDTO: Decodable, Identifiable, Hashable {
    let id: UUID
    let organization_slug: String
    let slug: String
    let title: String
    let description: String?
    let duration_min: Int
    let slot_interval_min: Int
    let buffer_before_min: Int
    let buffer_after_min: Int
    let min_notice_min: Int
    let date_window_days: Int
    let max_per_day: Int?
    let location_type: String
    let active: Bool
    let questions: [QuestionDTO]
    let kind: String
    let host_ids: [String]
    let capacity: Int
    let redirect_url: String?
}

/// Ce que la mise à jour renvoie : l'objet complet, un champ changé.
struct TypeDeRendezVousModifie: Encodable {
    let title: String
    let duration_min: Int
    let slot_interval_min: Int
    let buffer_before_min: Int
    let buffer_after_min: Int
    let min_notice_min: Int
    let date_window_days: Int
    let max_per_day: Int?
    let location_type: String
    let active: Bool
    let questions: [QuestionDTO]
    let kind: String
    let host_ids: [String]
    let capacity: Int
    let redirect_url: String?

    /// Reprend tout d'un type existant, en ne changeant que ce qu'on demande.
    init(_ type: TypeDeRendezVousDTO, actif: Bool? = nil) {
        title = type.title
        duration_min = type.duration_min
        slot_interval_min = type.slot_interval_min
        buffer_before_min = type.buffer_before_min
        buffer_after_min = type.buffer_after_min
        min_notice_min = type.min_notice_min
        date_window_days = type.date_window_days
        max_per_day = type.max_per_day
        location_type = type.location_type
        active = actif ?? type.active
        questions = type.questions
        kind = type.kind
        host_ids = type.host_ids
        capacity = type.capacity
        redirect_url = type.redirect_url
    }
}

/// Les types de rendez-vous, et ce qu'on peut en faire depuis un téléphone.
///
/// Volontairement partiel : créer un type demande une quinzaine de réglages — intervalles,
/// tampons, préavis, fenêtre de réservation, questions — qui se règlent bien à un clavier
/// et mal à un pouce. Ce qu'on fait en mobilité, c'est vérifier ce qui est ouvert,
/// partager un lien, et couper un créneau qu'on ne veut plus.
actor TypesDeRendezVous {
    private let api: APIClient

    init(api: APIClient) { self.api = api }

    func lister() async throws -> [TypeDeRendezVousDTO] {
        let types: [TypeDeRendezVousDTO] = try await api.obtenir("v1/me/event-types")
        // Les actifs d'abord : c'est ce qu'on vient vérifier. À l'intérieur, l'ordre
        // alphabétique, stable d'une lecture à l'autre.
        return types.sorted {
            $0.active != $1.active
                ? $0.active
                : $0.title.localizedCaseInsensitiveCompare($1.title) == .orderedAscending
        }
    }

    /// Ouvre ou ferme un type, en renvoyant tout le reste inchangé.
    func basculer(_ type: TypeDeRendezVousDTO, actif: Bool) async throws {
        try await api.envoyerSansReponse(
            "PUT", "v1/me/event-types/\(type.id.uuidString)",
            TypeDeRendezVousModifie(type, actif: actif))
    }

    func supprimer(_ id: UUID) async throws {
        struct Rien: Encodable {}
        try await api.envoyerSansReponse("DELETE", "v1/me/event-types/\(id.uuidString)", Rien())
    }

    /// L'adresse publique où l'on réserve ce type.
    ///
    /// Construite depuis l'adresse du serveur que l'utilisateur a saisie, et non depuis
    /// une constante : chaque client a sa propre instance, et un lien vers le mauvais
    /// domaine ne mènerait nulle part — sans qu'aucune erreur ne le signale, puisque c'est
    /// le destinataire qui le découvrirait.
    nonisolated static func lienPublic(_ type: TypeDeRendezVousDTO, serveur: URL) -> URL? {
        var composants = URLComponents(url: serveur, resolvingAgainstBaseURL: false)
        composants?.path = "/\(type.organization_slug)/\(type.slug)"
        return composants?.url
    }
}
