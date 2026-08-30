import SwiftUI

/// Les créneaux qu'on propose à réserver.
///
/// Volontairement partiel, et l'écran le dit. Créer un type demande une quinzaine de
/// réglages — intervalles, tampons, préavis, fenêtre, questions — qui se règlent bien à
/// un clavier et mal à un pouce. Ce qu'on fait en mobilité, c'est vérifier ce qui est
/// ouvert, partager un lien, et couper un créneau qu'on ne veut plus.
struct TypesDeRendezVousView: View {
    @EnvironmentObject private var session: SessionStore

    @StateObject private var modele = ModeleDeTypes()
    @State private var aSupprimer: TypeDeRendezVousDTO?

    var body: some View {
        NavigationStack {
            GhostScreen {
                VStack(alignment: .leading, spacing: 16) { contenu }
            }
            .navigationTitle("Réservation")
            .navigationBarTitleDisplayMode(.inline)
            .refreshable { await modele.recharger(session) }
            .alert(
                "Supprimer ce type de rendez-vous ?", isPresented: presentation($aSupprimer),
                presenting: aSupprimer,
                actions: { type in
                    Button("Supprimer", role: .destructive) {
                        Task { await modele.supprimer(type, session) }
                        aSupprimer = nil
                    }
                    Button("Annuler", role: .cancel) { aSupprimer = nil }
                },
                message: { type in
                    // Le lien cesse de fonctionner : c'est la conséquence qui touche des
                    // gens à qui on l'a déjà envoyé, et elle ne se devine pas.
                    Text(
                        "« \(type.title) » disparaîtra et son lien public cessera de fonctionner pour tous ceux à qui vous l'avez envoyé."
                    )
                })
        }
        .tint(Color.gcAccentText)
        .task { await modele.demarrer(session) }
    }

    @ViewBuilder private var contenu: some View {
        if modele.chargement && modele.types.isEmpty {
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
        } else if modele.types.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Aucun type de rendez-vous.")
                    .foregroundStyle(Color.gcInk)
                Text(
                    "Ils se créent depuis l'application web : une quinzaine de réglages qui se posent mieux à un clavier."
                )
                .font(.footnote)
                .foregroundStyle(Color.gcMuted)
                .fixedSize(horizontal: false, vertical: true)
            }
            .glassCard()
        } else {
            ForEach(modele.types) { type in
                LigneDeType(
                    type: type, lien: modele.lien(type, session),
                    basculer: { Task { await modele.basculer(type, session) } },
                    supprimer: { aSupprimer = type })
            }
        }
    }

    private func presentation<T>(_ valeur: Binding<T?>) -> Binding<Bool> {
        Binding(
            get: { valeur.wrappedValue != nil },
            set: { presente in if !presente { valeur.wrappedValue = nil } })
    }
}

private struct LigneDeType: View {
    let type: TypeDeRendezVousDTO
    let lien: URL?
    let basculer: () -> Void
    let supprimer: () -> Void

    var body: some View {
        GhostSection(titre: LocalizedStringKey(type.title)) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    Label {
                        Text("\(type.duration_min) min")
                    } icon: {
                        Image(systemName: "clock")
                    }
                    .font(.subheadline)
                    .foregroundStyle(Color.gcInk)

                    if !type.active {
                        Text("Fermé")
                            .font(.caption2.weight(.medium))
                            .foregroundStyle(Color.gcMuted)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(Color.gcMuted.opacity(0.16), in: Capsule())
                    }
                    Spacer(minLength: 4)
                }

                if let description = type.description, !description.isEmpty {
                    Text(verbatim: description)
                        .font(.footnote)
                        .foregroundStyle(Color.gcMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if let lien {
                    // Le lien se partage : c'est le geste principal de cet écran. On le
                    // montre en entier plutôt que caché derrière une icône — c'est ce
                    // qu'on relit pour vérifier qu'on envoie la bonne adresse.
                    ShareLink(item: lien) {
                        Label {
                            Text(verbatim: lien.absoluteString).lineLimit(1).truncationMode(.middle)
                        } icon: {
                            Image(systemName: "square.and.arrow.up")
                        }
                        .font(.footnote)
                    }
                    .foregroundStyle(Color.gcAccentText)
                    .accessibilityIdentifier("button.shareLink")
                }

                HStack(spacing: 12) {
                    Button(type.active ? "Fermer les réservations" : "Rouvrir", action: basculer)
                        .buttonStyle(SecondaryButtonStyle())
                        .accessibilityIdentifier("button.toggleType")
                    Spacer(minLength: 4)
                    Button(action: supprimer) {
                        Image(systemName: "trash")
                            .font(.system(size: 15, weight: .medium))
                            .frame(width: 34, height: 34)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(Color.gcDanger)
                    .accessibilityLabel("Supprimer")
                    .accessibilityIdentifier("button.deleteType")
                }
            }
            .padding(14)
        }
    }
}

@MainActor
final class ModeleDeTypes: ObservableObject {
    @Published private(set) var types: [TypeDeRendezVousDTO] = []
    @Published private(set) var chargement = false
    @Published private(set) var erreur: String?

    private var chargeUneFois = false

    func demarrer(_ session: SessionStore) async {
        guard !chargeUneFois else { return }
        chargeUneFois = true
        await recharger(session)
    }

    func lien(_ type: TypeDeRendezVousDTO, _ session: SessionStore) -> URL? {
        guard let serveur = AdresseDeServeur.normaliser(session.serveur) else { return nil }
        return TypesDeRendezVous.lienPublic(type, serveur: serveur)
    }

    func recharger(_ session: SessionStore) async {
        guard let api = session.api else { return }
        chargement = true
        defer { chargement = false }
        erreur = nil
        do {
            types = try await TypesDeRendezVous(api: api).lister()
        } catch {
            erreur = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func basculer(_ type: TypeDeRendezVousDTO, _ session: SessionStore) async {
        await agir(session) { service in
            try await service.basculer(type, actif: !type.active)
        }
    }

    func supprimer(_ type: TypeDeRendezVousDTO, _ session: SessionStore) async {
        await agir(session) { service in try await service.supprimer(type.id) }
    }

    private func agir(_ session: SessionStore, _ action: (TypesDeRendezVous) async throws -> Void)
        async
    {
        guard let api = session.api else { return }
        erreur = nil
        do {
            try await action(TypesDeRendezVous(api: api))
            await recharger(session)
        } catch {
            erreur = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}
