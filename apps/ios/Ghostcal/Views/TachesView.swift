import SwiftUI

/// Les tâches : ce qu'il reste à faire.
///
/// Une saisie en tête d'écran plutôt qu'un bouton « + » qui ouvre une feuille. Une tâche
/// s'ajoute en marchant, souvent d'une main, et chaque écran interposé entre l'intention
/// et le texte fait renoncer — on la note ailleurs, et elle n'entre jamais.
struct TachesView: View {
    @EnvironmentObject private var session: SessionStore
    let organisation: UUID?

    @StateObject private var modele = ModeleDeTaches()
    @State private var saisie = ""
    @State private var aSupprimer: Tache?

    var body: some View {
        NavigationStack {
            GhostScreen {
                VStack(alignment: .leading, spacing: 16) {
                    ajout
                    contenu
                }
            }
            .navigationTitle("Tâches")
            .navigationBarTitleDisplayMode(.inline)
            .refreshable { await modele.recharger(session, organisation) }
            .alert(
                "Supprimer cette tâche ?", isPresented: presentation($aSupprimer),
                presenting: aSupprimer,
                actions: { tache in
                    Button("Supprimer", role: .destructive) {
                        Task { await modele.supprimer(tache, session, organisation) }
                        aSupprimer = nil
                    }
                    Button("Annuler", role: .cancel) { aSupprimer = nil }
                },
                message: { _ in
                    Text("Elle disparaîtra définitivement. Le serveur ne garde pas de corbeille.")
                })
        }
        .tint(Color.gcAccentText)
        .task { await modele.demarrer(session, organisation) }
        .onChange(of: organisation) { _, nouvelle in
            Task { await modele.recharger(session, nouvelle) }
        }
    }

    private var ajout: some View {
        HStack(spacing: 10) {
            TextField(
                "", text: $saisie,
                prompt: Text("Ajouter une tâche").foregroundColor(Color.gcMuted.opacity(0.7))
            )
            .foregroundStyle(Color.gcInk)
            .submitLabel(.done)
            .onSubmit { ajouter() }
            .accessibilityIdentifier("field.newTask")

            Button("Ajouter", action: ajouter)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(vide ? Color.gcMuted : Color.gcAccentText)
                .disabled(vide || modele.occupe)
                .accessibilityIdentifier("button.addTask")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(Color.gcSurface.opacity(0.7), in: RoundedRectangle(cornerRadius: GC.radius))
        .overlay(
            RoundedRectangle(cornerRadius: GC.radius)
                .strokeBorder(Color.gcBorder, lineWidth: 1))
    }

    private var vide: Bool { saisie.trimmingCharacters(in: .whitespaces).isEmpty }

    @ViewBuilder private var contenu: some View {
        if modele.chargement && modele.taches.isEmpty {
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
        } else if modele.taches.isEmpty {
            Text("Rien à faire. C'est peut-être vrai.")
                .foregroundStyle(Color.gcMuted)
                .glassCard()
        } else {
            GhostSection(titre: "À faire") {
                ForEach(modele.taches) { tache in
                    LigneDeTache(
                        tache: tache,
                        basculer: { Task { await modele.basculer(tache, session, organisation) } },
                        supprimer: { aSupprimer = tache })
                    if tache.id != modele.taches.last?.id { GhostDivider() }
                }
            }
        }
    }

    private func ajouter() {
        let titre = saisie.trimmingCharacters(in: .whitespaces)
        guard !titre.isEmpty else { return }
        saisie = ""
        Task { await modele.ajouter(titre, session, organisation) }
    }

    /// Voir `FoldersView` de GhostPass : `.constant` empêcherait l'alerte suivante de
    /// s'afficher, SwiftUI la croyant toujours présentée.
    private func presentation<T>(_ valeur: Binding<T?>) -> Binding<Bool> {
        Binding(
            get: { valeur.wrappedValue != nil },
            set: { presente in if !presente { valeur.wrappedValue = nil } })
    }
}

private struct LigneDeTache: View {
    let tache: Tache
    let basculer: () -> Void
    let supprimer: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Button(action: basculer) {
                Image(systemName: tache.faite ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 20))
                    .foregroundStyle(tache.faite ? Color.gcAccentText : Color.gcMuted)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(tache.faite ? "Rouvrir" : "Terminer")
            .accessibilityIdentifier("button.toggleTask")

            VStack(alignment: .leading, spacing: 3) {
                titre
                if let echeance = tache.echeance {
                    Text(verbatim: echeance.formatted(date: .abbreviated, time: .shortened))
                        .font(.caption)
                        // Le retard se voit à la couleur : une date rouge se remarque sans
                        // qu'on ait à comparer mentalement avec aujourd'hui.
                        .foregroundStyle(tache.enRetard() ? Color.gcDanger : Color.gcMuted)
                }
                if let notes = tache.notes {
                    Text(verbatim: notes)
                        .font(.caption)
                        .foregroundStyle(Color.gcMuted)
                        .lineLimit(2)
                }
            }

            Spacer(minLength: 8)

            Button(action: supprimer) {
                Image(systemName: "trash")
                    .font(.system(size: 15, weight: .medium))
                    .frame(width: 34, height: 34)
            }
            .buttonStyle(.plain)
            .foregroundStyle(Color.gcDanger)
            .accessibilityLabel("Supprimer")
            .accessibilityIdentifier("button.deleteTask")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    @ViewBuilder private var titre: some View {
        switch tache.titre {
        case .dechiffre(let texte):
            Text(verbatim: texte)
                .font(.system(.body, weight: .medium))
                .foregroundStyle(tache.faite ? Color.gcMuted : Color.gcInk)
                .strikethrough(tache.faite)
                .lineLimit(2)
        case .sansTitre:
            Text("Sans titre")
                .font(.system(.body, weight: .medium))
                .foregroundStyle(Color.gcMuted)
        case .illisible:
            Label {
                Text("Chiffré — cette clé n'ouvre pas cette tâche")
            } icon: {
                Image(systemName: "lock.fill")
            }
            .font(.system(.subheadline, weight: .medium))
            .foregroundStyle(Color.gcMuted)
        }
    }
}

@MainActor
final class ModeleDeTaches: ObservableObject {
    @Published private(set) var taches: [Tache] = []
    @Published private(set) var chargement = false
    @Published private(set) var occupe = false
    @Published private(set) var erreur: String?

    private var chargeUneFois = false

    func demarrer(_ session: SessionStore, _ organisation: UUID?) async {
        guard !chargeUneFois else { return }
        chargeUneFois = true
        await recharger(session, organisation)
    }

    func recharger(_ session: SessionStore, _ organisation: UUID?) async {
        guard let api = session.api, let auth = session.auth, let organisation else { return }
        chargement = true
        defer { chargement = false }
        erreur = nil
        do {
            taches = try await Taches(api: api, auth: auth).lister(organisation: organisation)
        } catch {
            erreur = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func ajouter(_ titre: String, _ session: SessionStore, _ organisation: UUID?) async {
        await agir(session, organisation) { service, organisation in
            try await service.creer(titre: titre, echeance: nil, organisation: organisation)
        }
    }

    func basculer(_ tache: Tache, _ session: SessionStore, _ organisation: UUID?) async {
        await agir(session, organisation) { service, _ in
            try await service.marquer(tache.id, faite: !tache.faite)
        }
    }

    func supprimer(_ tache: Tache, _ session: SessionStore, _ organisation: UUID?) async {
        await agir(session, organisation) { service, _ in
            try await service.supprimer(tache.id)
        }
    }

    /// Agir puis relire, plutôt que de modifier la liste sur place.
    ///
    /// Une mise à jour optimiste afficherait une tâche cochée que le serveur aurait
    /// refusée. Relire coûte un aller-retour et dit la vérité — sur une liste de tâches,
    /// c'est le bon compromis ; sur une frappe au clavier, ce ne le serait pas.
    private func agir(
        _ session: SessionStore, _ organisation: UUID?,
        _ action: (Taches, UUID) async throws -> Void
    ) async {
        guard let api = session.api, let auth = session.auth, let organisation else { return }
        occupe = true
        defer { occupe = false }
        erreur = nil
        do {
            try await action(Taches(api: api, auth: auth), organisation)
            await recharger(session, organisation)
        } catch {
            erreur = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}
