import Foundation

/// Ouvrir une session GhostCal.
///
/// Deux choses se passent à la connexion, et il faut les distinguer parce qu'elles
/// échouent séparément :
///
/// 1. **L'authentification** — le serveur rend une paire de jetons. Sans elle, rien.
/// 2. **Le déverrouillage du coffre** — la phrase dérive une clé qui déballe la clé
///    privée de l'organisation. Sans lui, l'authentification a réussi mais l'agenda
///    reste illisible : les événements, les tâches et les noms des personnes qui ont
///    réservé sont scellés.
///
/// Un échec du second ne doit **jamais** empêcher le premier. C'est le comportement du
/// client web, et il est juste : quelqu'un dont le déverrouillage échoue doit pouvoir
/// entrer, voir qu'il est connecté, et comprendre que c'est sa phrase qui ne va pas —
/// pas se faire renvoyer à l'écran de connexion sans explication.
actor Auth {
    private let api: APIClient
    private var cles: [String: ClesOuvertes] = [:]

    init(api: APIClient) { self.api = api }

    /// Les clés déverrouillées d'une organisation, si elle l'a été.
    func clesDe(_ organisation: String) -> ClesOuvertes? { cles[organisation] }

    /// Le coffre est-il ouvert ? Faux juste après une connexion dont le déverrouillage a
    /// échoué — d'où la distinction avec « connecté ».
    var estDeverrouille: Bool { !cles.isEmpty }

    func verrouiller() { cles.removeAll() }

    // ─── Connexion ───

    struct Identifiants: Encodable {
        let email: String
        let password: String
    }

    /// Authentifie, puis tente d'ouvrir le coffre. Rend la raison d'un déverrouillage
    /// manqué plutôt que de la taire.
    @discardableResult
    func seConnecter(email: String, motDePasse: String) async throws -> String? {
        let jetons: JetonsDTO = try await api.envoyer(
            "POST", "v1/auth/login", Identifiants(email: email, password: motDePasse))
        await api.definirLesJetons(
            APIClient.Jetons(acces: jetons.access_token, rafraichissement: jetons.refresh_token))

        do {
            try await deverrouiller(phrase: motDePasse)
            return nil
        } catch {
            // Connecté sans coffre ouvert : on le dit, on ne défait pas la connexion.
            return (error as? LocalizedError)?.errorDescription
                ?? "Le coffre n'a pas pu être ouvert avec cette phrase."
        }
    }

    // ─── Déverrouillage ───

    /// Dérive la clé depuis la phrase, déballe chaque génération de clé d'organisation.
    ///
    /// La phrase peut être le mot de passe, la phrase de récupération, ou la phrase de
    /// chiffrement d'un compte SSO : le serveur range deux enveloppes par génération, et
    /// c'est le sel qui les distingue, pas la nature de ce qu'on tape.
    func deverrouiller(phrase: String, parRecuperation: Bool = false) async throws {
        let generations: [GenerationDeClesDTO] = try await api.obtenir("v1/auth/zk-keys")
        var ouvertes: [String: ClesOuvertes] = [:]

        for generation in generations {
            let enveloppe =
                parRecuperation
                ? generation.recovery_wrapped_private_key : generation.wrapped_private_key
            let selBrut = parRecuperation ? generation.recovery_salt : generation.wrap_salt
            guard let enveloppe, let selBrut, let sel = Data(base64Encoded: selBrut) else {
                continue
            }

            let cle = try deriverCle(phrase: phrase, sel: sel)
            let privee = try dechiffrerSymetrique(cle: cle, blob: enveloppe)
            guard let privee = String(data: privee, encoding: .utf8) else { continue }

            // Les générations d'une même organisation arrivent de la plus récente à la
            // plus ancienne : la première ouverte est la courante, les suivantes servent
            // à lire ce qui a été scellé avant une rotation.
            if var deja = ouvertes[generation.organization_id] {
                deja = ClesOuvertes(
                    organisation: deja.organisation, publique: deja.publique,
                    privee: deja.privee, anterieures: deja.anterieures + [privee])
                ouvertes[generation.organization_id] = deja
            } else {
                ouvertes[generation.organization_id] = ClesOuvertes(
                    organisation: generation.organization_id,
                    publique: generation.public_key, privee: privee, anterieures: [])
            }
        }

        guard !ouvertes.isEmpty else { throw AuthError.phraseIncorrecte }
        cles = ouvertes
    }

    /// Scelle un contenu vers la clé publique **courante** de l'organisation.
    ///
    /// Toujours la courante, jamais une génération retirée : sceller avec une ancienne
    /// produirait un contenu que les membres n'ayant que la nouvelle ne pourraient pas
    /// ouvrir — et l'échec ne se verrait qu'au moment de la lecture, chez quelqu'un
    /// d'autre.
    func sceller(_ clair: Data, organisation: String, domaine: String = "ghostcal-zk-v1") throws
        -> String
    {
        guard let cles = cles[organisation] else { throw AuthError.coffreFerme }
        return try scellerVers(publique: cles.publique, clair: clair, domaine: domaine)
    }

    /// Ouvre un contenu scellé, en essayant les générations dans l'ordre.
    ///
    /// Aucun blob ne porte d'identifiant de clé : c'est l'authentification AES-GCM qui
    /// rejette les mauvaises. Essayer dans l'ordre n'est donc pas une approximation, c'est
    /// le protocole.
    func ouvrir(_ blob: String, organisation: String, domaine: String = "ghostcal-zk-v1") -> Data? {
        guard let cles = cles[organisation] else { return nil }
        for privee in [cles.privee] + cles.anterieures {
            if let clair = try? ouvrirSceau(privee: privee, blob: blob, domaine: domaine) {
                return clair
            }
        }
        return nil
    }
}

enum AuthError: LocalizedError {
    case phraseIncorrecte
    /// On a tenté d'écrire alors que les clés ne sont pas ouvertes. Distinct d'une phrase
    /// fausse : ici rien n'a été tenté, il n'y a simplement rien pour sceller.
    case coffreFerme

    var errorDescription: String? {
        switch self {
        case .coffreFerme:
            return "Le coffre est fermé : impossible de chiffrer ce contenu."
        case .phraseIncorrecte:
            // Ni « mot de passe » ni « phrase de récupération » : les trois chemins
            // aboutissent ici, et nommer le mauvais enverrait chercher à côté.
            return "Cette phrase n'ouvre pas le coffre."
        }
    }
}
