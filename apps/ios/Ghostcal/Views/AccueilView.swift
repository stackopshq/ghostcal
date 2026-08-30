import SwiftUI

/// Ce qu'on voit une fois le coffre ouvert.
///
/// Cinq onglets : l'agenda, les tâches, les réunions, les créneaux à réserver, et les
/// réglages — qui rassemblent disponibilités, sondages, profil et équipe. Une barre à huit
/// onglets ne se lit plus ; ces quatre-là ont en commun d'être ce qu'on ouvre pour
/// vérifier ou corriger, pas ce qu'on regarde en chemin. Un onglet par section plutôt qu'un
/// menu — sur un téléphone, ce qu'on consulte plusieurs fois par jour doit être à un
/// toucher, pas à deux.
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
            ReunionsView(organisation: modele.organisationCourante)
                .tabItem { Label("Réunions", systemImage: "person.2") }
            TypesDeRendezVousView()
                .tabItem { Label("Réservation", systemImage: "link") }
            ReglagesView()
                .tabItem { Label("Réglages", systemImage: "gearshape") }
        }
        .tint(Color.gcAccentText)
    }
}
