import Foundation

/// Une réunion réservée, telle que le serveur la rend.
///
/// Le partage entre clair et scellé est plus subtil ici qu'ailleurs, et il vaut d'être
/// compris avant de toucher à l'écran :
///
/// - `event_title` est **en clair** : c'est le nom du type de rendez-vous, celui que le
///   visiteur a lu sur la page de réservation. Il n'a jamais été secret ;
/// - `invitee_email` est en clair aussi — le serveur doit envoyer les confirmations et
///   les rappels ;
/// - `invitee_name` est **nul** pour une réservation prise depuis une page publique : le
///   vrai nom est dans `invitee_private`, scellé. Il ne l'est pas pour une réunion créée
///   autrement. Le traiter comme toujours présent afficherait « Sans nom » là où le nom
///   existe, chiffré, juste à côté.
struct ReunionDTO: Decodable {
    let id: UUID
    let event_title: String
    let invitee_name: String?
    /// Optionnel **par prudence**, alors que le serveur le rend toujours aujourd'hui.
    ///
    /// Une décision prise cette nuit (ADR-0038) prévoit un mode où l'identité de l'invité
    /// est scellée vers la clé de l'organisation : l'adresse cesserait alors d'être en
    /// clair. Avec un champ obligatoire, le décodage de **toute la liste** échouerait —
    /// l'écran des réunions deviendrait vide chez qui choisit ce mode, sans rapport
    /// apparent avec la cause.
    ///
    /// Ce n'est pas de l'anticipation gratuite : un client qui perd un écran entier parce
    /// qu'un champ est devenu facultatif est fragile indépendamment de cette décision.
    let invitee_email: String?
    let invitee_timezone: String
    let start_at: Date
    let end_at: Date
    let status: String
    let location: String?
    let meeting_url: String?
    let invitee_private: String?
}

/// Ce que l'invité a écrit, une fois ouvert. Même forme que le client web —
/// `frontend/src/lib/zk.ts`, `InviteePrivate`.
struct ContenuDInvite: Codable, Equatable {
    var name: String
    var answers: [String: String]
    var notes: String
}

/// Une réunion, contenu ouvert quand on a pu.
struct Reunion: Identifiable, Hashable {
    let id: UUID
    let intitule: String
    let debut: Date
    let fin: Date
    let statut: Statut
    /// Vide quand le serveur ne le rend pas. L'écran retombe alors sur le nom déchiffré,
    /// et à défaut ne montre rien plutôt qu'une ligne vide qui ressemblerait à un défaut.
    let courriel: String
    let fuseau: String
    let lieu: String?
    let adresse: URL?
    let invite: NomDInvite
    let reponses: [(String, String)]
    let notes: String?

    /// Le nom de l'invité, et d'où il vient.
    enum NomDInvite: Hashable {
        case enClair(String)
        case dechiffre(String)
        /// Scellé, non ouvert. On affiche alors l'adresse e-mail, qui est en clair : mieux
        /// vaut identifier la personne par son adresse que ne rien montrer du tout.
        case illisible
        case inconnu
    }

    enum Statut: String {
        case confirmee = "confirmed"
        case annulee = "cancelled"
        case autre

        init(_ brut: String) { self = Statut(rawValue: brut) ?? .autre }
    }

    static func == (a: Reunion, b: Reunion) -> Bool { a.id == b.id }
    func hash(into hacheur: inout Hasher) { hacheur.combine(id) }
}

/// Lire et annuler les réunions.
actor Reunions {
    /// À venir, ou passées. Le serveur tranche : demander les deux et filtrer ici
    /// obligerait à télécharger un historique entier pour afficher trois lignes.
    enum Portee: String {
        case aVenir = "upcoming"
        case passees = "past"
    }

    private let api: APIClient
    private let auth: Auth

    init(api: APIClient, auth: Auth) {
        self.api = api
        self.auth = auth
    }

    func lister(_ portee: Portee, organisation: UUID) async throws -> [Reunion] {
        let brutes: [ReunionDTO] = try await api.obtenir(
            "v1/me/meetings", ["scope": portee.rawValue])

        var resultat: [Reunion] = []
        for brute in brutes {
            var invite = Reunion.NomDInvite.inconnu
            var reponses: [(String, String)] = []
            var notes: String?

            if let enClair = brute.invitee_name, !enClair.isEmpty {
                invite = .enClair(enClair)
            }
            if let scelle = brute.invitee_private {
                if let clair = await auth.ouvrir(scelle, organisation: organisation.uuidString),
                    let contenu = try? JSONDecoder().decode(ContenuDInvite.self, from: clair)
                {
                    if !contenu.name.isEmpty { invite = .dechiffre(contenu.name) }
                    // Trié : un dictionnaire n'a pas d'ordre, et une liste de réponses qui
                    // change d'ordre à chaque affichage donne l'impression que le contenu
                    // bouge.
                    reponses = contenu.answers.sorted { $0.key < $1.key }.map { ($0.key, $0.value) }
                    notes = contenu.notes.isEmpty ? nil : contenu.notes
                } else if case .inconnu = invite {
                    invite = .illisible
                }
            }

            resultat.append(
                Reunion(
                    id: brute.id, intitule: brute.event_title, debut: brute.start_at,
                    fin: brute.end_at, statut: Reunion.Statut(brute.status),
                    courriel: brute.invitee_email ?? "", fuseau: brute.invitee_timezone,
                    lieu: brute.location, adresse: brute.meeting_url.flatMap(URL.init(string:)),
                    invite: invite, reponses: reponses, notes: notes))
        }
        // À venir : la plus proche d'abord. Passées : la plus récente d'abord — on remonte
        // le temps quand on cherche dans un historique.
        return resultat.sorted {
            portee == .aVenir ? $0.debut < $1.debut : $0.debut > $1.debut
        }
    }

    func annuler(_ id: UUID) async throws {
        struct Rien: Encodable {}
        try await api.envoyerSansReponse("POST", "v1/me/meetings/\(id.uuidString)/cancel", Rien())
    }
}
