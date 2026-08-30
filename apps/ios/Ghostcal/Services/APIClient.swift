import Foundation

/// Erreurs que le serveur sait produire, et qu'il faut distinguer.
///
/// Le détail d'une réponse d'erreur prend **deux formes** selon son origine : une chaîne
/// pour les refus métier, un tableau d'objets `{loc, msg, type}` pour la validation
/// Pydantic. Un décodeur qui n'attend qu'une chaîne échoue sur les 422 — c'est-à-dire
/// précisément là où le serveur explique ce qui ne va pas.
enum APIError: LocalizedError, Equatable {
    case badURL
    case http(status: Int, detail: String)
    case malformedResponse

    var errorDescription: String? {
        switch self {
        case .badURL: return "Adresse de serveur invalide."
        case .http(_, let detail): return detail
        case .malformedResponse: return "Réponse inattendue du serveur."
        }
    }

    /// Le jeton est-il en cause ? Sert à décider d'un rafraîchissement.
    ///
    /// **Un 403 n'est pas un 401.** Le serveur rend 403 pour « pas membre de cette
    /// organisation », « rôle insuffisant », « mot de passe actuel faux », « adresse non
    /// vérifiée » — aucun de ces cas ne se répare en renouvelant le jeton. Les confondre
    /// enverrait l'application boucler sur un rafraîchissement qui réussit sans rien
    /// changer.
    var estUnProblemeDeJeton: Bool {
        if case .http(let status, _) = self { return status == 401 }
        return false
    }
}

/// Client HTTP de l'API GhostCal.
///
/// Deux particularités du serveur sont câblées ici plutôt que laissées à chaque appel :
///
/// 1. **`X-Organization-Id`.** Le serveur applique `FORCE ROW LEVEL SECURITY` : chaque
///    transaction pose l'organisation courante, et les politiques filtrent ligne à ligne.
///    Sans cet en-tête, il retient l'organisation **la plus ancienne** de l'utilisateur.
///    Un client qui l'oublie ne reçoit pas d'erreur : il lit silencieusement les données
///    d'une autre équipe que celle affichée. C'est la panne la plus coûteuse à
///    diagnostiquer, parce qu'elle ressemble à un succès.
///
/// 2. **Le rafraîchissement du jeton.** L'accès vaut quinze minutes, le rafraîchissement
///    trente jours, et le second **tourne** : celui que rend le serveur remplace le
///    précédent. Le conserver est obligatoire, sous peine de déconnexion au bout d'un
///    cycle.
actor APIClient {
    private let base: URL
    private let session: URLSession
    private var jetons: Jetons?
    /// L'organisation dont on lit les données. `nil` laisse le serveur choisir la plus
    /// ancienne — acceptable seulement avant que la liste des organisations soit connue.
    private var organisation: UUID?

    struct Jetons: Codable, Equatable {
        var acces: String
        var rafraichissement: String
    }

    init(base: URL, session: URLSession = .shared) {
        self.base = base
        self.session = session
    }

    func definirLesJetons(_ jetons: Jetons?) { self.jetons = jetons }
    func jetonsCourants() -> Jetons? { jetons }
    func definirLOrganisation(_ id: UUID?) { organisation = id }

    // ─── Appels ───

    func obtenir<T: Decodable>(_ chemin: String, _ requete: [String: String] = [:]) async throws
        -> T
    {
        try decoder(await appeler("GET", chemin, requete: requete, corps: nil))
    }

    func envoyer<T: Decodable, C: Encodable>(
        _ methode: String, _ chemin: String, _ corps: C
    ) async throws -> T {
        try decoder(await appeler(methode, chemin, corps: JSONEncoder.api.encode(corps)))
    }

    /// Pour les routes qui ne rendent rien d'exploitable — 204, ou un corps qu'on ignore.
    @discardableResult
    func envoyerSansReponse<C: Encodable>(
        _ methode: String, _ chemin: String, _ corps: C? = Optional<String>.none
    ) async throws -> Data {
        let donnees = try corps.map { try JSONEncoder.api.encode($0) }
        return try await appeler(methode, chemin, corps: donnees)
    }

    // ─── Mécanique ───

    private func appeler(
        _ methode: String, _ chemin: String, requete: [String: String] = [:], corps: Data?,
        dejaRafraichi: Bool = false
    ) async throws -> Data {
        guard
            var composants = URLComponents(
                url: base.appending(path: chemin), resolvingAgainstBaseURL: false)
        else { throw APIError.badURL }
        if !requete.isEmpty {
            composants.queryItems = requete.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let url = composants.url else { throw APIError.badURL }

        var requeteHTTP = URLRequest(url: url)
        requeteHTTP.httpMethod = methode
        requeteHTTP.httpBody = corps
        if corps != nil {
            requeteHTTP.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        if let jetons {
            requeteHTTP.setValue("Bearer \(jetons.acces)", forHTTPHeaderField: "Authorization")
        }
        if let organisation {
            requeteHTTP.setValue(organisation.uuidString, forHTTPHeaderField: "X-Organization-Id")
        }
        // Le serveur renvoie son propre `X-Request-ID` ; envoyer le nôtre permet de
        // retrouver une requête dans ses journaux à partir d'un rapport d'utilisateur.
        requeteHTTP.setValue(UUID().uuidString, forHTTPHeaderField: "X-Request-ID")

        let (donnees, reponse) = try await session.data(for: requeteHTTP)
        guard let http = reponse as? HTTPURLResponse else { throw APIError.malformedResponse }

        if (200..<300).contains(http.statusCode) { return donnees }

        // Un 401 se répare peut-être en renouvelant le jeton ; une seule fois, sinon deux
        // jetons périmés feraient boucler l'application.
        if http.statusCode == 401, !dejaRafraichi, jetons != nil {
            if await rafraichir() {
                return try await appeler(
                    methode, chemin, requete: requete, corps: corps, dejaRafraichi: true)
            }
        }
        throw APIError.http(status: http.statusCode, detail: Self.detail(donnees, http.statusCode))
    }

    /// Renouvelle la paire de jetons. Rend `false` si le rafraîchissement est refusé —
    /// il faut alors se reconnecter, et l'appelant doit le dire plutôt que de réessayer.
    private func rafraichir() async -> Bool {
        guard let courant = jetons else { return false }
        struct Corps: Encodable { let refresh_token: String }
        struct Reponse: Decodable {
            let access_token: String
            let refresh_token: String
        }
        var requete = URLRequest(url: base.appending(path: "v1/auth/refresh"))
        requete.httpMethod = "POST"
        requete.setValue("application/json", forHTTPHeaderField: "Content-Type")
        requete.httpBody = try? JSONEncoder.api.encode(
            Corps(refresh_token: courant.rafraichissement))
        guard let (donnees, reponse) = try? await session.data(for: requete),
            let http = reponse as? HTTPURLResponse, (200..<300).contains(http.statusCode),
            let nouveaux = try? JSONDecoder.api.decode(Reponse.self, from: donnees)
        else {
            jetons = nil
            return false
        }
        // Le jeton de rafraîchissement tourne : garder l'ancien déconnecterait au cycle
        // suivant.
        jetons = Jetons(acces: nouveaux.access_token, rafraichissement: nouveaux.refresh_token)
        return true
    }

    /// Le message d'erreur, quelle que soit la forme que le serveur lui donne.
    private static func detail(_ donnees: Data, _ statut: Int) -> String {
        struct Chaine: Decodable { let detail: String }
        struct Validation: Decodable {
            struct Entree: Decodable {
                let msg: String
            }
            let detail: [Entree]
        }
        if let simple = try? JSONDecoder().decode(Chaine.self, from: donnees) {
            return simple.detail
        }
        if let validation = try? JSONDecoder().decode(Validation.self, from: donnees) {
            return validation.detail.map(\.msg).joined(separator: " · ")
        }
        return "Erreur serveur (\(statut))."
    }

    private func decoder<T: Decodable>(_ donnees: Data) throws -> T {
        do {
            return try JSONDecoder.api.decode(T.self, from: donnees)
        } catch {
            throw APIError.malformedResponse
        }
    }
}

extension JSONDecoder {
    /// Le serveur date en ISO 8601 **avec offset**, et parfois avec des fractions de
    /// seconde. `.iso8601` seul échoue sur ces dernières.
    static let api: JSONDecoder = {
        let decodeur = JSONDecoder()
        decodeur.dateDecodingStrategy = .custom { decodeur in
            let texte = try decodeur.singleValueContainer().decode(String.self)
            if let date = ISO8601DateFormatter.avecFractions.date(from: texte) { return date }
            if let date = ISO8601DateFormatter.sansFractions.date(from: texte) { return date }
            throw DecodingError.dataCorruptedError(
                in: try decodeur.singleValueContainer(),
                debugDescription: "date ISO 8601 attendue, reçu « \(texte) »")
        }
        return decodeur
    }()
}

extension JSONEncoder {
    static let api: JSONEncoder = {
        let encodeur = JSONEncoder()
        encodeur.dateEncodingStrategy = .custom { date, encodeur in
            var conteneur = encodeur.singleValueContainer()
            try conteneur.encode(ISO8601DateFormatter.avecFractions.string(from: date))
        }
        return encodeur
    }()
}

extension ISO8601DateFormatter {
    static let avecFractions: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    static let sansFractions = ISO8601DateFormatter()
}
