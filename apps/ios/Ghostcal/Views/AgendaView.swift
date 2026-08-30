import SwiftUI

/// L'agenda : ce qui occupe les prochains jours.
///
/// Une liste plutôt qu'une grille. Une semaine en colonnes se lit sur un écran large ;
/// sur un téléphone tenu à une main, elle oblige à pincer pour lire un titre. Ce qu'on
/// vient vérifier en chemin, c'est « qu'est-ce que j'ai après », et une liste par jour y
/// répond directement.
struct AgendaView: View {
    @EnvironmentObject private var session: SessionStore
    /// Tenu par l'accueil : les deux onglets doivent parler de la même organisation, et un
    /// modèle par onglet les laisserait diverger sans que rien ne le signale.
    @ObservedObject var modele: ModeleDAgenda
    @State private var creation = false

    var body: some View {
        NavigationStack {
            GhostScreen {
                VStack(alignment: .leading, spacing: 16) {
                    if modele.organisations.count > 1 { selecteurDOrganisation }
                    contenu
                }
            }
            .navigationTitle("Agenda")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .primaryAction) { menu }
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        creation = true
                    } label: {
                        Image(systemName: "plus")
                    }
                    .accessibilityLabel("Nouveau rendez-vous")
                    .accessibilityIdentifier("button.newEvent")
                }
            }
            .sheet(isPresented: $creation) {
                NouvelEvenementView(organisation: modele.organisationCourante) {
                    await modele.recharger(session, gardantLesOrganisations: true)
                }
                .environmentObject(session)
            }
            .refreshable { await modele.recharger(session) }
        }
        .tint(Color.gcAccentText)
        .task { await modele.demarrer(session) }
    }

    @ViewBuilder private var contenu: some View {
        if modele.chargement && modele.jours.isEmpty {
            ProgressView().tint(Color.gcAccentText)
                .frame(maxWidth: .infinity, minHeight: 120)
        } else if let erreur = modele.erreur {
            VStack(alignment: .leading, spacing: 10) {
                Text(verbatim: erreur)
                    .foregroundStyle(Color.gcDanger)
                    .fixedSize(horizontal: false, vertical: true)
                Button("Réessayer") { Task { await modele.recharger(session) } }
                    .buttonStyle(SecondaryButtonStyle())
            }
            .glassCard()
        } else if modele.jours.isEmpty {
            Text("Rien de prévu dans les trente prochains jours.")
                .foregroundStyle(Color.gcMuted)
                .glassCard()
        } else {
            ForEach(modele.jours) { jour in
                GhostSection(titre: LocalizedStringKey(jour.intitule)) {
                    ForEach(jour.lignes) { ligne in
                        LigneDAgendaVue(ligne: ligne)
                        if ligne.id != jour.lignes.last?.id { GhostDivider() }
                    }
                }
            }
        }
    }

    private var selecteurDOrganisation: some View {
        GhostSection(titre: "Organisation") {
            Picker(
                selection: Binding(
                    get: { modele.organisationCourante },
                    set: { id in Task { await modele.choisir(id, session) } })
            ) {
                ForEach(modele.organisations) { organisation in
                    Text(verbatim: organisation.name).tag(Optional(organisation.id))
                }
            } label: {
                EmptyView()
            }
            .pickerStyle(.menu)
            .tint(Color.gcAccentText)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(14)
            .accessibilityIdentifier("picker.organisation")
        }
    }

    private var menu: some View {
        Menu {
            Button("Verrouiller le coffre") { Task { await session.verrouiller() } }
            Button("Se déconnecter", role: .destructive) { Task { await session.seDeconnecter() } }
        } label: {
            Image(systemName: "ellipsis.circle")
        }
        .accessibilityIdentifier("button.menu")
    }
}

/// Une ligne d'agenda.
private struct LigneDAgendaVue: View {
    let ligne: LigneDAgenda

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            heures
            VStack(alignment: .leading, spacing: 3) {
                titre
                if let lieu = ligne.lieu {
                    Label {
                        Text(verbatim: lieu).lineLimit(1)
                    } icon: {
                        Image(systemName: "mappin.and.ellipse")
                    }
                    .font(.caption)
                    .foregroundStyle(Color.gcMuted)
                }
            }
            Spacer(minLength: 4)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    @ViewBuilder private var titre: some View {
        switch ligne.titre {
        case .dechiffre(let texte), .enClair(let texte):
            Text(verbatim: texte)
                .font(.system(.body, weight: .medium))
                .foregroundStyle(Color.gcInk)
                .lineLimit(2)
        case .sansTitre:
            Text("Sans titre")
                .font(.system(.body, weight: .medium))
                .foregroundStyle(Color.gcMuted)
        case .illisible:
            // Un trou visible, jamais une ligne absente : le créneau est occupé, et le
            // cacher ferait croire à une disponibilité. Le dire permet aussi de
            // comprendre qu'il s'agit d'une clé manquante, pas d'un événement perdu.
            Label {
                Text("Chiffré — cette clé n'ouvre pas cet événement")
            } icon: {
                Image(systemName: "lock.fill")
            }
            .font(.system(.subheadline, weight: .medium))
            .foregroundStyle(Color.gcMuted)
        }
    }

    private var heures: some View {
        VStack(alignment: .trailing, spacing: 2) {
            if ligne.journeeEntiere {
                Text("Journée")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Color.gcAccentText)
            } else {
                Text(verbatim: ligne.debut.formatted(date: .omitted, time: .shortened))
                    .font(.caption.weight(.semibold).monospacedDigit())
                    .foregroundStyle(Color.gcAccentText)
                Text(verbatim: ligne.fin.formatted(date: .omitted, time: .shortened))
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(Color.gcMuted)
            }
        }
        .frame(width: 54, alignment: .trailing)
    }
}

/// Ce que l'écran doit savoir, tenu hors de la vue.
@MainActor
final class ModeleDAgenda: ObservableObject {
    struct Jour: Identifiable {
        let id: Date
        let intitule: String
        let lignes: [LigneDAgenda]
    }

    @Published private(set) var jours: [Jour] = []
    @Published private(set) var organisations: [OrganisationDTO] = []
    @Published private(set) var organisationCourante: UUID?
    @Published private(set) var chargement = false
    @Published private(set) var erreur: String?

    /// Trente jours : assez pour « qu'est-ce que j'ai le mois prochain », loin de la borne
    /// de 366 jours que le serveur impose pour ne pas développer une série sans fin.
    private let fenetre: TimeInterval = 30 * 24 * 3600

    func demarrer(_ session: SessionStore) async {
        guard organisations.isEmpty else { return }
        await recharger(session)
    }

    func choisir(_ organisation: UUID?, _ session: SessionStore) async {
        organisationCourante = organisation
        await session.api?.definirLOrganisation(organisation)
        await recharger(session, gardantLesOrganisations: true)
    }

    func recharger(_ session: SessionStore, gardantLesOrganisations: Bool = false) async {
        guard let api = session.api, let auth = session.auth else { return }
        chargement = true
        defer { chargement = false }
        erreur = nil

        let service = Agenda(api: api, auth: auth)
        do {
            if !gardantLesOrganisations {
                organisations = try await service.organisations()
                // Sans choix explicite le serveur retient la plus ancienne : on pose la
                // même, sinon l'écran afficherait une organisation et lirait les clés
                // d'une autre.
                if organisationCourante == nil { organisationCourante = organisations.first?.id }
                await api.definirLOrganisation(organisationCourante)
            }
            guard let organisation = organisationCourante else {
                jours = []
                return
            }
            let debut = Date()
            let lignes = try await service.lignes(
                de: debut, a: debut.addingTimeInterval(fenetre), organisation: organisation)
            jours = Self.parJour(lignes)
        } catch {
            erreur = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    /// Regroupe par journée civile, dans le fuseau de l'appareil.
    ///
    /// Le serveur date en UTC ; grouper sur ces dates brutes mettrait un rendez-vous de
    /// 23 h 30 au lendemain pour qui vit à l'est de Greenwich.
    /// `nonisolated` : la fonction est pure — des lignes en entrée, des jours en sortie.
    /// La lier au fil principal parce que la classe l'est obligeait les tests à s'y
    /// rendre pour vérifier une opération qui ne touche à aucun état.
    nonisolated static func parJour(_ lignes: [LigneDAgenda]) -> [Jour] {
        let calendrier = Calendar.current
        let groupes = Dictionary(grouping: lignes) { calendrier.startOfDay(for: $0.debut) }
        return groupes.keys.sorted().map { jour in
            Jour(
                id: jour,
                intitule: jour.formatted(
                    .dateTime.weekday(.wide).day().month(.wide)),
                lignes: groupes[jour]?.sorted { $0.debut < $1.debut } ?? [])
        }
    }
}
