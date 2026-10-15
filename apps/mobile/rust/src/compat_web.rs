//! Envelopes in the GhostCal **web** format, so web and mobile read each other.
//!
//! The shared core (`ghost-crypto`) seals with XChaCha20-Poly1305 and a versioned
//! envelope `{v, nonce, encrypted_target, epk}`. The GhostCal web client has not
//! migrated: it still uses AES-256-GCM with a 12-byte nonce and no `v`
//! (`frontend/src/lib/e2e.ts`). Key derivation is the same on both sides — Argon2id
//! for passphrases, X25519 → HKDF-SHA256 (info = domain) for seals — only the final
//! AEAD differs. Without this module, an account created on the web could not be
//! unlocked on mobile, and what the mobile wrote could not be read on the web.
//!
//! Rule: **read both, write the web format**, until the web moves to the shared core.
//! An envelope with a `v` field is the core's and goes to `ghost_crypto::zk`.

use aes_gcm::aead::{Aead, KeyInit, Payload};
use aes_gcm::{Aes256Gcm, Nonce};
use base64::engine::general_purpose::STANDARD as B64;
use base64::Engine as _;
use ghost_crypto::zk;
use hkdf::Hkdf;
use rand_core::{OsRng, RngCore};
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use x25519_dalek::{PublicKey, StaticSecret};

const NONCE_WEB: usize = 12;
const CLE: usize = 32;

/// `SEQUENCE { INTEGER 0, SEQUENCE { OID 1.3.101.110 }, OCTET STRING { OCTET STRING (32) } }`:
/// the PKCS#8 wrapping WebCrypto exports an X25519 private key in.
const PREFIXE_PKCS8_X25519: [u8; 16] = [
    0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x6e, 0x04, 0x22, 0x04, 0x20,
];

#[derive(Deserialize)]
struct Lue {
    v: Option<u8>,
    nonce: String,
    encrypted_target: String,
    epk: Option<String>,
}

#[derive(Serialize)]
struct Ecrite {
    nonce: String,
    encrypted_target: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    epk: Option<String>,
}

fn lire(blob: &str) -> Result<Lue, String> {
    serde_json::from_str(blob).map_err(|_| "enveloppe illisible".to_string())
}

fn cle_de(octets: &[u8]) -> Result<[u8; CLE], String> {
    octets.try_into().map_err(|_| "clé de longueur invalide".to_string())
}

fn aes_chiffrer(cle: &[u8; CLE], clair: &[u8]) -> Result<(String, String), String> {
    let mut nonce = [0u8; NONCE_WEB];
    OsRng.fill_bytes(&mut nonce);
    let corps = Aes256Gcm::new(cle.into())
        .encrypt(Nonce::from_slice(&nonce), Payload { msg: clair, aad: b"" })
        .map_err(|_| "chiffrement impossible".to_string())?;
    Ok((B64.encode(nonce), B64.encode(corps)))
}

fn aes_dechiffrer(cle: &[u8; CLE], nonce_b64: &str, corps_b64: &str) -> Result<Vec<u8>, String> {
    let nonce = B64.decode(nonce_b64).map_err(|_| "nonce illisible".to_string())?;
    let corps = B64.decode(corps_b64).map_err(|_| "corps illisible".to_string())?;
    if nonce.len() != NONCE_WEB {
        return Err("nonce de longueur invalide".into());
    }
    Aes256Gcm::new(cle.into())
        .decrypt(Nonce::from_slice(&nonce), Payload { msg: &corps, aad: b"" })
        .map_err(|_| "déchiffrement impossible".to_string())
}

/// X25519 then HKDF-SHA256 with an empty salt and the domain as info — the same
/// derivation as the web (`ecdhAesKey`) and the core (`cle_aead`).
fn cle_partagee(secret: &StaticSecret, pair: &PublicKey, domaine: &str) -> [u8; CLE] {
    let partage = secret.diffie_hellman(pair);
    let hk = Hkdf::<Sha256>::new(None, partage.as_bytes());
    let mut cle = [0u8; CLE];
    hk.expand(domaine.as_bytes(), &mut cle)
        .expect("32 bytes is a valid HKDF-SHA256 length");
    cle
}

pub fn chiffrer_symetrique(cle: &[u8], clair: &[u8]) -> Result<String, String> {
    let (nonce, encrypted_target) = aes_chiffrer(&cle_de(cle)?, clair)?;
    serde_json::to_string(&Ecrite { nonce, encrypted_target, epk: None }).map_err(|e| e.to_string())
}

pub fn dechiffrer_symetrique(cle: &[u8], blob: &str) -> Result<Vec<u8>, String> {
    let env = lire(blob)?;
    if env.v.is_some() {
        return zk::dechiffrer_symetrique(cle, blob).map_err(|e| e.to_string());
    }
    aes_dechiffrer(&cle_de(cle)?, &env.nonce, &env.encrypted_target)
}

pub fn sceller_vers(publique_b64: &str, clair: &[u8], domaine: &str) -> Result<String, String> {
    let brut = B64.decode(publique_b64).map_err(|_| "clé publique illisible".to_string())?;
    let destinataire = PublicKey::from(cle_de(&brut)?);
    let ephemere = StaticSecret::random_from_rng(OsRng);
    let epk = PublicKey::from(&ephemere);
    let cle = cle_partagee(&ephemere, &destinataire, domaine);
    let (nonce, encrypted_target) = aes_chiffrer(&cle, clair)?;
    serde_json::to_string(&Ecrite { nonce, encrypted_target, epk: Some(B64.encode(epk.as_bytes())) })
        .map_err(|e| e.to_string())
}

pub fn ouvrir_sceau(privee_b64: &str, blob: &str, domaine: &str) -> Result<Vec<u8>, String> {
    let env = lire(blob)?;
    if env.v.is_some() {
        return zk::ouvrir_sceau(privee_b64, blob, domaine).map_err(|e| e.to_string());
    }
    let pkcs8 = B64.decode(privee_b64).map_err(|_| "clé privée illisible".to_string())?;
    if pkcs8.len() != PREFIXE_PKCS8_X25519.len() + CLE || pkcs8[..16] != PREFIXE_PKCS8_X25519 {
        return Err("clé privée qui n'est pas une X25519 PKCS#8".into());
    }
    let secret = StaticSecret::from(cle_de(&pkcs8[16..])?);
    let epk_b64 = env.epk.ok_or("sceau sans clé éphémère")?;
    let epk = B64.decode(epk_b64).map_err(|_| "clé éphémère illisible".to_string())?;
    let cle = cle_partagee(&secret, &PublicKey::from(cle_de(&epk)?), domaine);
    aes_dechiffrer(&cle, &env.nonce, &env.encrypted_target)
}

#[cfg(test)]
mod tests {
    use super::*;

    // Vectors produced by Node's WebCrypto with the exact steps of
    // frontend/src/lib/e2e.ts (encryptSymmetric, sealToPublicKey); see the PR.
    include!("vecteurs_web.rs");

    #[test]
    fn reads_a_web_symmetric_envelope() {
        let cle = B64.decode(CLE_SYM).unwrap();
        assert_eq!(dechiffrer_symetrique(&cle, BLOB_SYM).unwrap(), CLAIR.as_bytes());
    }

    #[test]
    fn reads_a_web_seal() {
        assert_eq!(ouvrir_sceau(PRIVEE_PKCS8, BLOB_SCEAU, "ghostcal-zk-v1").unwrap(), CLAIR.as_bytes());
    }

    #[test]
    fn writes_what_it_reads_in_web_format() {
        let cle = [7u8; 32];
        let blob = chiffrer_symetrique(&cle, b"bonjour").unwrap();
        assert!(!blob.contains("\"v\""), "the web does not know the v field");
        assert_eq!(dechiffrer_symetrique(&cle, &blob).unwrap(), b"bonjour");

        let scelle = sceller_vers(PUBLIQUE, b"bonjour", "ghostcal-zk-v1").unwrap();
        assert!(scelle.contains("\"epk\""));
        assert_eq!(ouvrir_sceau(PRIVEE_PKCS8, &scelle, "ghostcal-zk-v1").unwrap(), b"bonjour");
    }

    #[test]
    fn still_reads_the_core_format() {
        let cle = [9u8; 32];
        let coeur = zk::chiffrer_symetrique(&cle, b"ancien").unwrap();
        assert!(coeur.contains("\"v\""));
        assert_eq!(dechiffrer_symetrique(&cle, &coeur).unwrap(), b"ancien");
    }

    #[test]
    fn a_wrong_key_fails_instead_of_returning_garbage() {
        let blob = chiffrer_symetrique(&[1u8; 32], b"x").unwrap();
        assert!(dechiffrer_symetrique(&[2u8; 32], &blob).is_err());
    }

    /// Prints envelopes for the reverse check (Node decrypts what Rust wrote):
    /// `cargo test emit -- --ignored --nocapture`.
    #[test]
    #[ignore]
    fn emit_for_node() {
        let cle = B64.decode(CLE_SYM).unwrap();
        println!("SYM={}", chiffrer_symetrique(&cle, CLAIR.as_bytes()).unwrap());
        println!("SEAL={}", sceller_vers(PUBLIQUE, CLAIR.as_bytes(), "ghostcal-zk-v1").unwrap());
    }
}
