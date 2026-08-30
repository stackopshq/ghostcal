import Foundation

/// Une tâche, telle que le serveur la rend.
///
/// L'échéance est **en clair**, le contenu non. Ce n'est pas une inconséquence : le
/// serveur trie par échéance et envoie les rappels, deux choses qu'il ne saurait pas faire
/// sur une date scellée. Il sait donc *quand*, jamais *quoi*.
struct TacheDTO: Decodable {
    let id: UUID
    let content: String?
    let due_at: Date?
    let completed: Bool
    let completed_at: Date?
    let created_at: Date
    let reminder_minutes: Int?
}

/// Ce que contient une tâche, une fois ouverte. Même forme que le client web —
/// `frontend/src/lib/zk.ts`, `TaskContent`.
struct ContenuDeTache: Codable, Equatable {
    var title: String
    var notes: String
}

/// Une tâche, contenu ouvert quand on a pu.
struct Tache: Identifiable, Hashable {
    let id: UUID
    let titre: Titre
    let notes: String?
    let echeance: Date?
    let faite: Bool
    let creee: Date

    /// Les mêmes distinctions que pour l'agenda : une tâche qu'on ne sait pas ouvrir n'est
    /// ni une tâche sans titre, ni une tâche absente.
    enum Titre: Hashable {
        case dechiffre(String)
        case illisible
        case sansTitre
    }

    /// En retard ? Une échéance dépassée sur une tâche non faite. Calculé ici plutôt qu'à
    /// l'affichage : c'est une propriété de la tâche, pas une décoration.
    func enRetard(_ maintenant: Date = Date()) -> Bool {
        guard let echeance, !faite else { return false }
        return echeance < maintenant
    }
}

/// Lire et écrire les tâches.
actor Taches {
    private let api: APIClient
    private let auth: Auth

    init(api: APIClient, auth: Auth) {
        self.api = api
        self.auth = auth
    }

    func lister(organisation: UUID) async throws -> [Tache] {
        let brutes: [TacheDTO] = try await api.obtenir("v1/me/tasks")
        var resultat: [Tache] = []
        for brute in brutes {
            var titre = Tache.Titre.sansTitre
            var notes: String?
            if let scelle = brute.content {
                if let clair = await auth.ouvrir(scelle, organisation: organisation.uuidString),
                    let contenu = try? JSONDecoder().decode(ContenuDeTache.self, from: clair)
                {
                    titre = .dechiffre(contenu.title)
                    notes = contenu.notes.isEmpty ? nil : contenu.notes
                } else {
                    titre = .illisible
                }
            }
            resultat.append(
                Tache(
                    id: brute.id, titre: titre, notes: notes, echeance: brute.due_at,
                    faite: brute.completed, creee: brute.created_at))
        }
        return Self.ordonner(resultat)
    }

    /// L'ordre d'affichage : ce qui presse d'abord, ce qui est fait à la fin.
    ///
    /// Le serveur ne peut pas trier sur le titre — il ne le lit pas — mais l'échéance est
    /// en clair, et c'est elle qui compte. Les tâches sans échéance viennent après celles
    /// qui en ont une : les mêler par date de création ferait remonter une note vieille de
    /// six mois au-dessus d'un rendez-vous de demain.
    nonisolated static func ordonner(_ taches: [Tache]) -> [Tache] {
        taches.sorted { a, b in
            if a.faite != b.faite { return !a.faite }
            switch (a.echeance, b.echeance) {
            case let (x?, y?): return x < y
            case (_?, nil): return true
            case (nil, _?): return false
            case (nil, nil): return a.creee > b.creee
            }
        }
    }

    /// Crée une tâche. Le contenu est scellé ici, l'échéance part en clair.
    @discardableResult
    func creer(titre: String, notes: String = "", echeance: Date?, organisation: UUID)
        async throws -> UUID
    {
        struct Corps: Encodable {
            let content: String
            let due_at: String?
        }
        struct Cree: Decodable { let id: UUID }

        let clair = try JSONEncoder().encode(ContenuDeTache(title: titre, notes: notes))
        let scelle = try await auth.sceller(clair, organisation: organisation.uuidString)
        let formateur = ISO8601DateFormatter()
        formateur.formatOptions = [.withInternetDateTime]
        let reponse: Cree = try await api.envoyer(
            "POST", "v1/me/tasks",
            Corps(content: scelle, due_at: echeance.map(formateur.string(from:))))
        return reponse.id
    }

    func marquer(_ id: UUID, faite: Bool) async throws {
        struct Corps: Encodable { let completed: Bool }
        try await api.envoyerSansReponse(
            "POST", "v1/me/tasks/\(id.uuidString)/complete", Corps(completed: faite))
    }

    func supprimer(_ id: UUID) async throws {
        struct Rien: Encodable {}
        try await api.envoyerSansReponse("DELETE", "v1/me/tasks/\(id.uuidString)", Rien())
    }
}
