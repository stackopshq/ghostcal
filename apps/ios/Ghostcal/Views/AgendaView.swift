import SwiftUI

/// Ce qui vient après le déverrouillage.
///
/// Volontairement nu pour l'instant : la tranche d'authentification est écrite et
/// éprouvée, l'agenda ne l'est pas. Un écran qui afficherait des rendez-vous fictifs
/// donnerait l'illusion d'une fonctionnalité livrée — ce que la suite a déjà payé une
/// fois, avec un travail de CI qui paraissait vert alors qu'il était écarté.
struct AgendaView: View {
    @EnvironmentObject private var session: SessionStore

    var body: some View {
        NavigationStack {
            GhostScreen {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Coffre ouvert")
                        .font(.system(.title2, design: .rounded, weight: .bold))
                        .foregroundStyle(Color.gcInk)
                    Text(
                        "L'agenda, les tâches et les réunions arrivent. Ce qui est en place : la connexion, le déverrouillage du coffre et la lecture des clés d'organisation."
                    )
                    .foregroundStyle(Color.gcMuted)
                    .fixedSize(horizontal: false, vertical: true)
                }
                .glassCard()
            }
            .navigationTitle("GhostCal")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Menu {
                        Button("Verrouiller le coffre") { Task { await session.verrouiller() } }
                        Button("Se déconnecter", role: .destructive) {
                            Task { await session.seDeconnecter() }
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                    .accessibilityIdentifier("button.menu")
                }
            }
        }
        .tint(Color.gcAccentText)
    }
}
