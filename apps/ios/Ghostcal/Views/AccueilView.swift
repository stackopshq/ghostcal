import SwiftUI

/// Ce qu'on voit une fois le coffre ouvert.
///
/// Deux onglets, pas plus pour l'instant : l'agenda et les tâches. Les réunions viendront
/// s'y ajouter. Un onglet par section plutôt qu'un menu — sur un téléphone, ce qu'on
/// consulte plusieurs fois par jour doit être à un toucher, pas à deux.
///
/// L'organisation courante est choisie une fois et descend aux deux onglets : la choisir
/// dans chacun laisserait l'agenda sur une équipe et les tâches sur une autre, ce qui ne
/// se remarquerait qu'en cherchant longtemps une tâche qui existe pourtant.
struct AccueilView: View {
    @EnvironmentObject private var session: SessionStore
    @StateObject private var modele = ModeleDAgenda()

    var body: some View {
        TabView {
            AgendaView(modele: modele)
                .tabItem { Label("Agenda", systemImage: "calendar") }
            TachesView(organisation: modele.organisationCourante)
                .tabItem { Label("Tâches", systemImage: "checklist") }
        }
        .tint(Color.gcAccentText)
    }
}
