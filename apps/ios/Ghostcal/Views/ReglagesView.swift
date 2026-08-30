import SwiftUI

/// Le cinquième onglet : ce qui ne se consulte pas tous les jours.
///
/// Disponibilités, sondages, profil et équipe réunis plutôt qu'un onglet chacun. Une barre
/// à huit onglets ne se lit plus, et ces quatre-là ont en commun d'être ce qu'on ouvre
/// pour vérifier ou corriger, pas ce qu'on regarde en chemin.
struct ReglagesView: View {
    @EnvironmentObject private var session: SessionStore
    @StateObject private var modele = ModeleDeReglages()

    var body: some View {
        NavigationStack {
            GhostScreen {
                VStack(alignment: .leading, spacing: 16) {
                    if let erreur = modele.erreur {
                        Text(verbatim: erreur)
                            .font(.footnote)
                            .foregroundStyle(Color.gcDanger)
                            .fixedSize(horizontal: false, vertical: true)
                            .glassCard()
                    }
                    profil
                    disponibilites
                    sondages
                    equipe
                    compte
                }
            }
            .navigationTitle("Réglages")
            .navigationBarTitleDisplayMode(.inline)
            .refreshable { await modele.recharger(session) }
        }
        .tint(Color.gcAccentText)
        .task { await modele.demarrer(session) }
    }

    // ─── Profil ───

    @ViewBuilder private var profil: some View {
        if let profil = modele.profil {
            GhostSection(titre: "Profil") {
                VStack(alignment: .leading, spacing: 10) {
                    ligne("person", Text(verbatim: profil.name))
                    HStack(spacing: 6) {
                        ligne("envelope", Text(verbatim: profil.email))
                        if !profil.email_verified {
                            // Une adresse non vérifiée empêche les envois : le dire ici
                            // évite de chercher pourquoi les invités ne reçoivent rien.
                            Text("Non vérifiée")
                                .font(.caption2.weight(.medium))
                                .foregroundStyle(Color.gcDanger)
                                .padding(.horizontal, 7)
                                .padding(.vertical, 3)
                                .background(Color.gcDanger.opacity(0.16), in: Capsule())
                        }
                    }
                    ligne("globe", Text(verbatim: profil.timezone))
                }
                .padding(14)
            }
        }
    }

    // ─── Disponibilités ───

    @ViewBuilder private var disponibilites: some View {
        GhostSection(
            titre: "Disponibilités",
            note: "Les plages où les autres peuvent réserver. Elles se modifient sur le web."
        ) {
            if modele.horaires.isEmpty {
                Text("Aucun horaire défini.")
                    .font(.footnote)
                    .foregroundStyle(Color.gcMuted)
                    .padding(14)
            } else {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(modele.horaires) { horaire in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(verbatim: horaire.name)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(Color.gcInk)
                            Text(verbatim: horaire.timezone)
                                .font(.caption)
                                .foregroundStyle(Color.gcMuted)
                            ForEach(horaire.rules, id: \.self) { regle in
                                Text(verbatim: "\(regle.jour) · \(regle.start) – \(regle.end)")
                                    .font(.footnote.monospacedDigit())
                                    .foregroundStyle(Color.gcInk)
                            }
                            if !horaire.overrides.isEmpty {
                                Text("\(horaire.overrides.count) exception(s)")
                                    .font(.caption)
                                    .foregroundStyle(Color.gcMuted)
                            }
                        }
                        if horaire.id != modele.horaires.last?.id { GhostDivider() }
                    }
                }
                .padding(14)
            }
        }
    }

    // ─── Sondages ───

    @ViewBuilder private var sondages: some View {
        GhostSection(titre: "Sondages") {
            if modele.sondages.isEmpty {
                Text("Aucun sondage en cours.")
                    .font(.footnote)
                    .foregroundStyle(Color.gcMuted)
                    .padding(14)
            } else {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(modele.sondages) { sondage in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(verbatim: sondage.title)
                                .font(.subheadline.weight(.medium))
                                .foregroundStyle(Color.gcInk)
                            Text(
                                "\(sondage.option_count) créneau(x) · \(sondage.vote_count) vote(s)"
                            )
                            .font(.caption)
                            .foregroundStyle(Color.gcMuted)
                        }
                        if sondage.id != modele.sondages.last?.id { GhostDivider() }
                    }
                }
                .padding(14)
            }
        }
    }

    // ─── Équipe ───

    @ViewBuilder private var equipe: some View {
        GhostSection(titre: "Équipe") {
            if modele.membres.isEmpty {
                Text("Aucun membre à afficher.")
                    .font(.footnote)
                    .foregroundStyle(Color.gcMuted)
                    .padding(14)
            } else {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(modele.membres) { membre in
                        HStack(spacing: 10) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(verbatim: membre.name)
                                    .font(.subheadline.weight(.medium))
                                    .foregroundStyle(Color.gcInk)
                                Text(verbatim: membre.email)
                                    .font(.caption)
                                    .foregroundStyle(Color.gcMuted)
                            }
                            Spacer(minLength: 8)
                            Text(verbatim: membre.role_lisible)
                                .font(.caption2.weight(.medium))
                                .foregroundStyle(Color.gcAccentText)
                                .padding(.horizontal, 7)
                                .padding(.vertical, 3)
                                .background(Color.gcAccent.opacity(0.16), in: Capsule())
                        }
                        if membre.id != modele.membres.last?.id { GhostDivider() }
                    }
                }
                .padding(14)
            }
        }
    }

    // ─── Compte ───

    private var compte: some View {
        GhostSection(titre: "Session") {
            VStack(alignment: .leading, spacing: 10) {
                Button("Verrouiller le coffre") { Task { await session.verrouiller() } }
                    .buttonStyle(SecondaryButtonStyle())
                    .accessibilityIdentifier("button.lock")
                Button("Se déconnecter", role: .destructive) {
                    Task { await session.seDeconnecter() }
                }
                .buttonStyle(SecondaryButtonStyle())
                .accessibilityIdentifier("button.signOut")
                Text(
                    "Verrouiller referme le coffre sans quitter la session : il faudra retaper la phrase, pas le mot de passe."
                )
                .font(.caption)
                .foregroundStyle(Color.gcMuted)
                .fixedSize(horizontal: false, vertical: true)
            }
            .padding(14)
        }
    }

    private func ligne(_ icone: String, _ texte: Text) -> some View {
        Label {
            texte.font(.subheadline).foregroundStyle(Color.gcInk)
        } icon: {
            Image(systemName: icone).foregroundStyle(Color.gcMuted)
        }
    }
}

@MainActor
final class ModeleDeReglages: ObservableObject {
    @Published private(set) var profil: ProfilDTO?
    @Published private(set) var horaires: [HoraireDTO] = []
    @Published private(set) var sondages: [SondageDTO] = []
    @Published private(set) var membres: [MembreDTO] = []
    @Published private(set) var erreur: String?

    private var chargeUneFois = false

    func demarrer(_ session: SessionStore) async {
        guard !chargeUneFois else { return }
        chargeUneFois = true
        await recharger(session)
    }

    /// Quatre lectures indépendantes, et l'échec de l'une ne doit pas emporter les autres.
    ///
    /// Un membre sans droit sur l'équipe reçoit un 403 sur cette seule liste : tout
    /// abandonner lui montrerait un écran vide alors que son profil et ses disponibilités
    /// sont parfaitement lisibles. On garde donc la première erreur pour la dire, et on
    /// affiche tout ce qui a répondu.
    func recharger(_ session: SessionStore) async {
        guard let api = session.api else { return }
        let service = Reglages(api: api)
        erreur = nil

        do { profil = try await service.profil() } catch { noter(error) }
        do { horaires = try await service.horaires() } catch { noter(error) }
        do { sondages = try await service.sondages() } catch { noter(error) }
        do { membres = try await service.membres() } catch { noter(error) }
    }

    private func noter(_ erreurSurvenue: Error) {
        guard erreur == nil else { return }
        erreur =
            (erreurSurvenue as? LocalizedError)?.errorDescription
            ?? erreurSurvenue.localizedDescription
    }
}
