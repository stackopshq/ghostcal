import Foundation

/// Ce que le serveur rend à la connexion.
struct JetonsDTO: Decodable {
    let access_token: String
    let refresh_token: String
    let expires_in: Int
}

/// Une génération de clés d'organisation, telle que `GET /v1/auth/zk-keys` la rend.
///
/// Le serveur en renvoie **plusieurs**, la plus récente d'abord. Un blob scellé ne porte
/// aucun identifiant de clé : on essaie la génération courante, puis les précédentes, et
/// c'est l'authentification AES-GCM qui rejette les mauvaises. Perdre les anciennes
/// générations rendrait illisible tout ce qui a été scellé avant une rotation.
struct GenerationDeClesDTO: Decodable {
    let organization_id: String
    /// La clé publique de cette génération. Tout ce qu'on crée est scellé vers celle de la
    /// génération courante — sans elle, l'application ne saurait que lire.
    let public_key: String
    let sealed_org_key: String?
    let wrapped_private_key: String
    let wrap_salt: String
    let recovery_wrapped_private_key: String?
    let recovery_salt: String?
}

private struct ClesZkDTO: Decodable {
    let keys: [GenerationDeClesDTO]
}

/// La paire de clés personnelle, distincte de celle de l'organisation.
struct PaireDeClesDTO: Decodable {
    let public_key: String
    let wrapped_private_key: String
    let wrap_salt: String
}

/// Les clés déverrouillées d'une organisation, gardées en mémoire.
///
/// **Elles ne descendent pas dans le cœur.** Le binding expose la cryptographie ; où
/// dorment les clés est une politique de plateforme — trousseau ici, Keystore sur
/// Android, `sessionStorage` au navigateur. Les faire descendre derrière UniFFI
/// recréerait une divergence dès qu'une plateforme en réclame une autre.
struct ClesOuvertes {
    let organisation: String
    /// La clé publique **courante**. C'est vers elle que tout nouveau contenu est scellé,
    /// jamais vers une génération retirée : ce qui serait scellé avec une ancienne
    /// deviendrait illisible pour qui n'a que la nouvelle.
    let publique: String
    /// La clé privée X25519, en PKCS#8 base64 — la forme que le cœur attend.
    let privee: String
    /// Les générations précédentes, à essayer dans l'ordre pour ce qui est plus ancien
    /// qu'une rotation.
    let anterieures: [String]
}
