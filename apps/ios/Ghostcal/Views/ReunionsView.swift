import SwiftUI

/// Les réunions réservées par d'autres sur vos créneaux.
///
/// À venir par défaut : c'est ce qu'on vient vérifier. L'historique est à un toucher, pas
/// à zéro — on l'ouvre pour retrouver quelque chose, pas pour le consulter chaque matin.
struct ReunionsView: View {
    @EnvironmentObject private var session: SessionStore
    let organisation: UUID?

    @StateObject private var modele = ModeleDeReunions()
    @State private var aAnnuler: Reunion?

    var body: some View {
        NavigationStack {
            GhostScreen {
                VStack(alignment: .leading, spacing: 16) {
                    selecteur
                    contenu
                }
            }
            .navigationTitle("Réunions")
            .navigationBarTitleDisplayMode(.inline)
            .refreshable { await modele.recharger(session, organisation) }
            .alert(
                "Annuler cette réunion ?", isPresented: presentation($aAnnuler),
                presenting: aAnnuler,
                actions: { reunion in
                    Button("Annuler la réunion", role: .destructive) {
                        Task { await modele.annuler(reunion, session, organisation) }
                        aAnnuler = nil
                    }
                    Button("Ne rien faire", role: .cancel) { aAnnuler = nil }
                },
                message: { reunion in
                    // Dire que l'invité sera prévenu : c'est le geste qui touche quelqu'un
                    // d'autre, et il vaut mieux le savoir avant que de le découvrir après.
                    // L'adresse peut ne pas être en clair : dire « et  en sera informé »
                    // avec un trou serait plus inquiétant que de ne pas la nommer.
                    reunion.courriel.isEmpty
                        ? Text("« \(reunion.intitule) » sera annulée et l'invité en sera informé.")
                        : Text(
                            "« \(reunion.intitule) » sera annulée et \(reunion.courriel) en sera informé."
                        )
                })
        }
        .tint(Color.gcAccentText)
        .task { await modele.demarrer(session, organisation) }
        .onChange(of: organisation) { _, nouvelle in
            Task { await modele.recharger(session, nouvelle) }
        }
    }

    private var selecteur: some View {
        Picker("", selection: portee) {
            Text("À venir").tag(Reunions.Portee.aVenir)
            Text("Passées").tag(Reunions.Portee.passees)
        }
        .pickerStyle(.segmented)
        .accessibilityIdentifier("picker.scope")
    }

    private var portee: Binding<Reunions.Portee> {
        Binding(
            get: { modele.portee },
            set: { nouvelle in Task { await modele.choisir(nouvelle, session, organisation) } })
    }

    @ViewBuilder private var contenu: some View {
        if modele.chargement && modele.reunions.isEmpty {
            ProgressView().tint(Color.gcAccentText)
                .frame(maxWidth: .infinity, minHeight: 120)
        } else if let erreur = modele.erreur {
            VStack(alignment: .leading, spacing: 10) {
                Text(verbatim: erreur)
                    .foregroundStyle(Color.gcDanger)
                    .fixedSize(horizontal: false, vertical: true)
                Button("Réessayer") { Task { await modele.recharger(session, organisation) } }
                    .buttonStyle(SecondaryButtonStyle())
            }
            .glassCard()
        } else if modele.reunions.isEmpty {
            Text(
                modele.portee == .aVenir
                    ? "Aucune réunion à venir." : "Aucune réunion passée."
            )
            .foregroundStyle(Color.gcMuted)
            .glassCard()
        } else {
            ForEach(modele.reunions) { reunion in
                LigneDeReunion(
                    reunion: reunion,
                    annuler: reunion.statut == .confirmee && modele.portee == .aVenir
                        ? { aAnnuler = reunion } : nil)
            }
        }
    }

    /// Voir `TachesView` : `.constant` empêcherait l'alerte suivante de s'afficher.
    private func presentation<T>(_ valeur: Binding<T?>) -> Binding<Bool> {
        Binding(
            get: { valeur.wrappedValue != nil },
            set: { presente in if !presente { valeur.wrappedValue = nil } })
    }
}

private struct LigneDeReunion: View {
    let reunion: Reunion
    let annuler: (() -> Void)?

    var body: some View {
        GhostSection(titre: LocalizedStringKey(reunion.intitule)) {
            VStack(alignment: .leading, spacing: 10) {
                entete
                invite
                if let lieu = reunion.lieu, !lieu.isEmpty {
                    ligne("mappin.and.ellipse", Text(verbatim: lieu))
                }
                if let adresse = reunion.adresse {
                    Link(destination: adresse) {
                        ligne("video", Text(verbatim: adresse.host ?? adresse.absoluteString))
                    }
                    .foregroundStyle(Color.gcAccentText)
                }
                if !reunion.reponses.isEmpty { reponses }
                if let notes = reunion.notes { ligne("text.alignleft", Text(verbatim: notes)) }
                if let annuler {
                    Button("Annuler la réunion", role: .destructive, action: annuler)
                        .buttonStyle(SecondaryButtonStyle())
                        .accessibilityIdentifier("button.cancelMeeting")
                }
            }
            .padding(14)
        }
    }

    private var entete: some View {
        HStack(spacing: 8) {
            Text(verbatim: reunion.debut.formatted(date: .abbreviated, time: .shortened))
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Color.gcInk)
            if reunion.statut == .annulee {
                Text("Annulée")
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(Color.gcDanger)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(Color.gcDanger.opacity(0.16), in: Capsule())
            }
        }
    }

    @ViewBuilder private var invite: some View {
        switch reunion.invite {
        case .enClair(let nom), .dechiffre(let nom):
            ligne(
                "person",
                Text(verbatim: reunion.courriel.isEmpty ? nom : "\(nom) · \(reunion.courriel)"))
        case .illisible:
            // Le nom est scellé et cette clé ne l'ouvre pas. Quand l'adresse est en clair,
            // elle identifie tout de même la personne — mieux que rien, et le cadenas dit
            // pourquoi le nom manque. Quand elle ne l'est pas non plus, on le dit aussi :
            // une ligne muette ressemblerait à un défaut d'affichage.
            ligne(
                "lock",
                reunion.courriel.isEmpty
                    ? Text("Invité chiffré") : Text(verbatim: reunion.courriel))
        case .inconnu:
            ligne(
                "person",
                reunion.courriel.isEmpty
                    ? Text("Invité inconnu") : Text(verbatim: reunion.courriel))
        }
    }

    private var reponses: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(reunion.reponses, id: \.0) { question, reponse in
                VStack(alignment: .leading, spacing: 2) {
                    Text(verbatim: question)
                        .font(.caption)
                        .foregroundStyle(Color.gcMuted)
                    Text(verbatim: reponse)
                        .font(.subheadline)
                        .foregroundStyle(Color.gcInk)
                }
            }
        }
    }

    private func ligne(_ icone: String, _ texte: Text) -> some View {
        Label {
            texte.font(.subheadline).foregroundStyle(Color.gcInk)
        } icon: {
            Image(systemName: icone).foregroundStyle(Color.gcMuted)
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}

@MainActor
final class ModeleDeReunions: ObservableObject {
    @Published private(set) var reunions: [Reunion] = []
    @Published private(set) var portee: Reunions.Portee = .aVenir
    @Published private(set) var chargement = false
    @Published private(set) var erreur: String?

    private var chargeUneFois = false

    func demarrer(_ session: SessionStore, _ organisation: UUID?) async {
        guard !chargeUneFois else { return }
        chargeUneFois = true
        await recharger(session, organisation)
    }

    func choisir(_ nouvelle: Reunions.Portee, _ session: SessionStore, _ organisation: UUID?) async
    {
        portee = nouvelle
        reunions = []
        await recharger(session, organisation)
    }

    func recharger(_ session: SessionStore, _ organisation: UUID?) async {
        guard let api = session.api, let auth = session.auth, let organisation else { return }
        chargement = true
        defer { chargement = false }
        erreur = nil
        do {
            reunions = try await Reunions(api: api, auth: auth)
                .lister(portee, organisation: organisation)
        } catch {
            erreur = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func annuler(_ reunion: Reunion, _ session: SessionStore, _ organisation: UUID?) async {
        guard let api = session.api, let auth = session.auth, let organisation else { return }
        erreur = nil
        do {
            try await Reunions(api: api, auth: auth).annuler(reunion.id)
            await recharger(session, organisation)
        } catch {
            erreur = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}
