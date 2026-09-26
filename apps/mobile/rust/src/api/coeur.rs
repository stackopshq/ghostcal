//! Ce que Dart peut appeler du cœur commun.
//!
//! **Aucune cryptographie ici.** Cette façade traduit des types — `Vec<u8>` contre
//! `&[u8]`, `String` contre `&str` — et rien d'autre. La règle qui a rendu possible le
//! passage à Flutter est celle-là : pas une ligne de crypto hors du cœur. La réécriture
//! porte sur l'interface, jamais sur le produit.

use ghost_crypto::zk;

/// L'erreur telle que Dart la verra.
///
/// Le type d'erreur du cœur ne traverse pas : il porte des variantes qui n'ont de sens
/// qu'en Rust. On rend un message, comme le fait déjà le binding UniFFI — ce qui compte,
/// c'est que l'échec soit un échec, pas qu'il soit typé de l'autre côté.
#[derive(Debug)]
pub struct ErreurDuCoeur {
    pub message: String,
}

impl<E: std::fmt::Display> From<E> for ErreurDuCoeur {
    fn from(erreur: E) -> Self {
        Self { message: erreur.to_string() }
    }
}

/// Dérive la clé de coffre depuis une phrase et un sel.
///
/// Le vecteur qui l'éprouve vient de `hash-wasm`, la bibliothèque Argon2 du navigateur —
/// pas du cœur. C'est ce qui rend le test utile : il vérifie que Dart obtient ce que le
/// web obtient, et non que le cœur est cohérent avec lui-même.
pub fn deriver_cle(phrase: String, sel: Vec<u8>) -> Result<Vec<u8>, ErreurDuCoeur> {
    Ok(zk::deriver_cle(&phrase, &sel)?.to_vec())
}

/// Scelle un contenu vers une clé publique, dans un domaine donné.
pub fn sceller_vers(
    publique: String,
    clair: Vec<u8>,
    domaine: String,
) -> Result<String, ErreurDuCoeur> {
    Ok(zk::sceller_vers(&publique, &clair, &domaine)?)
}

/// Ouvre un contenu scellé. Échoue si le domaine ne correspond pas — c'est cette
/// séparation qui empêche ghostcal et ghostmail de lire les données l'un de l'autre.
pub fn ouvrir_sceau(
    privee: String,
    blob: String,
    domaine: String,
) -> Result<Vec<u8>, ErreurDuCoeur> {
    Ok(zk::ouvrir_sceau(&privee, &blob, &domaine)?)
}

/// Déballe un contenu chiffré symétriquement — l'enveloppe d'une clé privée
/// d'organisation, scellée sous la clé dérivée de la phrase.
pub fn dechiffrer_symetrique(cle: Vec<u8>, blob: String) -> Result<Vec<u8>, ErreurDuCoeur> {
    Ok(zk::dechiffrer_symetrique(&cle, &blob)?)
}

/// L'opération inverse, pour réenvelopper une clé lors d'un changement de phrase.
pub fn chiffrer_symetrique(cle: Vec<u8>, clair: Vec<u8>) -> Result<String, ErreurDuCoeur> {
    Ok(zk::chiffrer_symetrique(&cle, &clair)?)
}

/// Une paire de clés X25519, en base64.
pub struct PaireDeCles {
    pub publique: String,
    pub privee: String,
}

pub fn generer_paire() -> PaireDeCles {
    let paire = zk::generer_paire();
    PaireDeCles { publique: paire.publique, privee: paire.privee }
}
