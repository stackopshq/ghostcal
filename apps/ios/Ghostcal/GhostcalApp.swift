import SwiftUI

/// Point d'entrée de GhostCal iOS.
///
/// Le cœur cryptographique commun à la suite est branché : `tools/ios/build-xcframework.sh`
/// construit `ghost-crypto-ffi` depuis ghostsuite et en génère les bindings. Tout ce qui
/// est chiffré en dépend — les événements, les tâches, le nom des personnes qui ont
/// réservé — et la connexion elle-même : la phrase dérive la clé qui déballe la clé privée
/// de l'organisation.
@main
struct GhostcalApp: App {
    @StateObject private var session = SessionStore()

    var body: some Scene {
        WindowGroup {
            Group {
                switch session.etat {
                case .ouvert:
                    AccueilView()
                case .dehors, .coffreFerme:
                    ConnexionView()
                }
            }
            .environmentObject(session)
        }
    }
}
