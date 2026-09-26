//! Fabrique le matériel de clés d'un compte de banc, avec **le cœur de la suite**.
//!
//! `tools/banc-local.sh` s'en sert pour amorcer un compte jetable. Réimplémenter Argon2id
//! et l'enveloppe en Python ou en shell aurait donné un banc qui prouve la cohérence du
//! script avec lui-même, et rien sur le produit : c'est le même cœur que l'application qui
//! doit produire ces octets.
//!
//!   amorcer cles <phrase> <phrase-de-recuperation>   → le corps de POST /v1/auth/zk-keys
//!   amorcer sceller <publique-b64> <texte>           → un contenu scellé, prêt à poster
use std::env;

use ghost_crypto::zk;

const DOMAINE: &str = "ghostcal-zk-v1";

/// Enveloppe une clé privée sous une phrase, et rend le sel qui va avec.
///
/// Le sel fait 16 octets, comme partout dans la suite : c'est ce que `contrat.json` fixe,
/// et une autre taille rendrait les enveloppes illisibles par les autres clients.
fn envelopper(privee: &str, phrase: &str) -> (String, String) {
    let mut sel = [0u8; 16];
    getrandom::fill(&mut sel).expect("le générateur du système a échoué");
    let cle = zk::deriver_cle(phrase, &sel).expect("dérivation impossible");
    let enveloppe = zk::chiffrer_symetrique(&cle, privee.as_bytes()).expect("chiffrement impossible");
    (enveloppe, base64_standard(&sel))
}

fn base64_standard(octets: &[u8]) -> String {
    use base64::Engine as _;
    base64::engine::general_purpose::STANDARD.encode(octets)
}

fn main() {
    let arguments: Vec<String> = env::args().collect();
    match arguments.get(1).map(String::as_str) {
        Some("cles") => {
            let phrase = arguments.get(2).expect("phrase manquante");
            let recuperation = arguments.get(3).expect("phrase de récupération manquante");
            let paire = zk::generer_paire();
            let (par_phrase, sel) = envelopper(&paire.privee, phrase);
            let (par_recuperation, sel_recuperation) = envelopper(&paire.privee, recuperation);
            // Encodé par serde, jamais par interpolation : **l'enveloppe est elle-même
            // du JSON**, donc l'insérer brute casse le document extérieur. Le serveur
            // répond alors « JSON decode error » avec une position d'octet, ce qui
            // n'oriente vers rien.
            //
            // Les noms de champs sont ceux du serveur : les traduire serait la façon la
            // plus élégante de rendre le compte inutilisable.
            let corps = serde_json::json!({
                "public_key": paire.publique,
                "wrapped_private_key": par_phrase,
                "wrap_salt": sel,
                "recovery_wrapped_private_key": par_recuperation,
                "recovery_salt": sel_recuperation,
            });
            println!("{corps}");
        }
        Some("sceller") => {
            let publique = arguments.get(2).expect("clé publique manquante");
            let clair = arguments.get(3).expect("contenu manquant");
            print!(
                "{}",
                zk::sceller_vers(publique, clair.as_bytes(), DOMAINE).expect("scellement impossible")
            );
        }
        _ => {
            eprintln!("usage : amorcer cles <phrase> <récupération> | amorcer sceller <publique> <clair>");
            std::process::exit(2);
        }
    }
}
