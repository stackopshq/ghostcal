import SwiftUI

/// Point d'entrée de GhostCal iOS.
///
/// L'application est incomplète et le sait : le cœur cryptographique commun à la suite
/// est en cours d'extraction, et sans lui rien de chiffré ne s'ouvre — ni les événements,
/// ni les tâches, ni le nom des personnes qui ont réservé. La connexion elle-même en
/// dépend : le mot de passe dérive la clé qui déballe la clé privée de l'organisation.
///
/// Ce qui est bâti d'abord est donc ce qui n'en dépend pas : le client HTTP, la charte,
/// et les écrans dont les données voyagent en clair — types de rendez-vous,
/// disponibilités, sondages, statistiques, profil, équipe.
@main
struct GhostcalApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}

struct ContentView: View {
    var body: some View {
        GhostScreen {
            VStack(spacing: 14) {
                Text("GhostCal")
                    .font(.system(.largeTitle, design: .rounded, weight: .bold))
                    .foregroundStyle(Color.gcInk)
                Text("En construction.")
                    .foregroundStyle(Color.gcMuted)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 60)
        }
    }
}
