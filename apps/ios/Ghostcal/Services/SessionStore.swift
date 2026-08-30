import Foundation
import SwiftUI

/// L'état de la session, tel que les écrans le voient.
///
/// Trois états, et non deux — c'est la distinction que porte `Auth` et qu'il serait
/// tentant d'aplatir :
///
/// - **dehors** : aucun jeton ;
/// - **connecté, coffre fermé** : le serveur nous reconnaît, mais la phrase n'a pas
///   ouvert les clés. L'agenda existe et reste illisible ;
/// - **coffre ouvert** : tout est lisible.
///
/// Aplatir les deux derniers renverrait à l'écran de connexion quelqu'un qui est
/// parfaitement authentifié, sans lui dire que c'est sa phrase qui ne va pas.
@MainActor
final class SessionStore: ObservableObject {
    enum Etat: Equatable {
        case dehors
        case coffreFerme(raison: String?)
        case ouvert
    }

    @Published private(set) var etat: Etat = .dehors
    @Published private(set) var occupe = false
    @Published var erreur: String?

    /// L'adresse saisie, conservée entre deux lancements : la retaper à chaque fois
    /// serait la première friction d'une application qu'on ouvre dix fois par jour.
    @Published var serveur: String = Trousseau.lire(Trousseau.Cle.serveur) ?? ""
    @Published var email: String = Trousseau.lire(Trousseau.Cle.email) ?? ""

    private(set) var api: APIClient?
    private(set) var auth: Auth?

    /// Une session enregistrée attend-elle sa phrase ?
    ///
    /// On ne peut pas reprendre une session complètement : les jetons rouvrent le compte,
    /// jamais le coffre. L'écran demande donc la phrase seule, sans redemander l'adresse
    /// ni l'e-mail — c'est le cas courant au lancement.
    var sessionEnregistree: Bool {
        Trousseau.lire(Trousseau.Cle.jetonDeRafraichissement) != nil && !serveur.isEmpty
    }

    // ─── Entrée ───

    func seConnecter(motDePasse: String) async {
        guard let base = AdresseDeServeur.normaliser(serveur) else {
            erreur = "Adresse de serveur invalide."
            return
        }
        occupe = true
        defer { occupe = false }
        erreur = nil

        let client = APIClient(base: base)
        let service = Auth(api: client)
        do {
            let echecDuCoffre = try await service.seConnecter(email: email, motDePasse: motDePasse)
            api = client
            auth = service
            await enregistrer(client, base: base)
            etat = echecDuCoffre == nil ? .ouvert : .coffreFerme(raison: echecDuCoffre)
        } catch {
            erreur = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    /// Reprend la session enregistrée, puis ouvre le coffre avec la phrase donnée.
    func reprendre(phrase: String, parRecuperation: Bool = false) async {
        guard let base = AdresseDeServeur.normaliser(serveur),
            let acces = Trousseau.lire(Trousseau.Cle.jetonDAcces),
            let rafraichissement = Trousseau.lire(Trousseau.Cle.jetonDeRafraichissement)
        else {
            etat = .dehors
            return
        }
        occupe = true
        defer { occupe = false }
        erreur = nil

        let client = APIClient(base: base)
        await client.definirLesJetons(
            APIClient.Jetons(acces: acces, rafraichissement: rafraichissement))
        let service = Auth(api: client)
        do {
            try await service.deverrouiller(phrase: phrase, parRecuperation: parRecuperation)
            api = client
            auth = service
            // Les jetons ont pu tourner pendant l'appel : on réenregistre ceux qui valent.
            await enregistrer(client, base: base)
            etat = .ouvert
        } catch {
            // Un jeton périmé et une phrase fausse ne se corrigent pas de la même façon :
            // l'un demande de se reconnecter, l'autre de retaper. Les confondre enverrait
            // quelqu'un ressaisir une phrase juste.
            if await client.jetonsCourants() == nil {
                await seDeconnecter()
                erreur = "La session a expiré. Reconnectez-vous."
            } else {
                erreur =
                    (error as? LocalizedError)?.errorDescription
                    ?? "Le coffre n'a pas pu être ouvert avec cette phrase."
            }
        }
    }

    /// Ouvre le coffre d'une session déjà authentifiée — le cas « connecté, coffre fermé ».
    func deverrouiller(phrase: String, parRecuperation: Bool = false) async {
        guard let auth else { return }
        occupe = true
        defer { occupe = false }
        erreur = nil
        do {
            try await auth.deverrouiller(phrase: phrase, parRecuperation: parRecuperation)
            etat = .ouvert
        } catch {
            erreur =
                (error as? LocalizedError)?.errorDescription
                ?? "Le coffre n'a pas pu être ouvert avec cette phrase."
        }
    }

    func verrouiller() async {
        await auth?.verrouiller()
        etat = .coffreFerme(raison: nil)
    }

    func seDeconnecter() async {
        await auth?.verrouiller()
        await api?.definirLesJetons(nil)
        api = nil
        auth = nil
        Trousseau.retirer(Trousseau.Cle.jetonDAcces)
        Trousseau.retirer(Trousseau.Cle.jetonDeRafraichissement)
        etat = .dehors
    }

    private func enregistrer(_ client: APIClient, base: URL) async {
        Trousseau.poser(base.absoluteString, pour: Trousseau.Cle.serveur)
        Trousseau.poser(email, pour: Trousseau.Cle.email)
        guard let jetons = await client.jetonsCourants() else { return }
        Trousseau.poser(jetons.acces, pour: Trousseau.Cle.jetonDAcces)
        Trousseau.poser(jetons.rafraichissement, pour: Trousseau.Cle.jetonDeRafraichissement)
    }
}

/// Ce qu'on accepte comme adresse de serveur.
///
/// Taper « ghostcal.stackops.ch » est le geste naturel ; refuser au motif qu'il manque
/// « https:// » ferait échouer la toute première tentative de quelqu'un qui a pourtant
/// donné la bonne adresse. Même règle que GhostPass, y compris l'exception de la boucle
/// locale — un serveur de développement tourne en clair.
enum AdresseDeServeur {
    static func normaliser(_ saisie: String) -> URL? {
        let texte = saisie.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !texte.isEmpty else { return nil }
        let avecSchema =
            texte.contains("://")
            ? texte : (estBoucleLocale(texte) ? "http://" : "https://") + texte
        guard let url = URL(string: avecSchema), let schema = url.scheme?.lowercased(),
            schema == "https" || schema == "http", let hote = url.host, !hote.isEmpty
        else { return nil }
        return url
    }

    private static func estBoucleLocale(_ texte: String) -> Bool {
        let hote = texte.split(separator: "/").first.map(String.init) ?? texte
        let sansPort = hote.split(separator: ":").first.map(String.init) ?? hote
        return ["localhost", "127.0.0.1", "::1", "[::1]"].contains(sansPort.lowercased())
    }
}
