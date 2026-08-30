import SwiftUI

/// Un sondage : les créneaux proposés, qui a voté quoi, et le choix final.
///
/// Rien n'est chiffré ici non plus — les votants sont des invités sans clé, qui répondent
/// depuis un lien public. Ce que l'organisateur voit, un serveur curieux le verrait aussi.
/// C'est le prix d'un sondage ouvert à des gens qui n'ont pas de compte, et il vaut mieux
/// le savoir que le supposer.
struct SondageView: View {
    @EnvironmentObject private var session: SessionStore
    @Environment(\.dismiss) private var dismiss

    let sondage: SondageDTO
    /// Rappelé après un choix ou une annulation : la liste des réglages doit refléter
    /// l'état nouveau, sinon un sondage clos y resterait ouvert.
    let apres: () async -> Void

    @State private var detail: SondageDetailDTO?
    @State private var chargement = true
    @State private var erreur: String?
    @State private var aRetenir: OptionDeSondageDTO?

    var body: some View {
        NavigationStack {
            GhostScreen {
                VStack(alignment: .leading, spacing: 16) {
                    if chargement && detail == nil {
                        ProgressView().tint(Color.gcAccentText)
                            .frame(maxWidth: .infinity, minHeight: 120)
                    }
                    if let erreur {
                        Text(verbatim: erreur)
                            .font(.footnote)
                            .foregroundStyle(Color.gcDanger)
                            .fixedSize(horizontal: false, vertical: true)
                            .glassCard()
                    }
                    if let detail {
                        creneaux(detail)
                        votants(detail)
                        actions(detail)
                    }
                }
            }
            .navigationTitle(Text(verbatim: sondage.title))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Fermer") { dismiss() }
                        .foregroundStyle(Color.gcAccentText)
                }
            }
            .alert(
                "Retenir ce créneau ?", isPresented: presentation($aRetenir),
                presenting: aRetenir,
                actions: { option in
                    Button("Retenir") {
                        Task { await finaliser(option) }
                        aRetenir = nil
                    }
                    Button("Annuler", role: .cancel) { aRetenir = nil }
                },
                message: { option in
                    // Deux conséquences que rien à l'écran ne laisse deviner : le sondage
                    // se ferme, et un rendez-vous apparaît dans l'agenda.
                    Text(
                        "Le sondage se fermera et le rendez-vous du \(option.start_at.formatted(date: .abbreviated, time: .shortened)) sera créé."
                    )
                })
        }
        .tint(Color.gcAccentText)
        .task { await charger() }
    }

    private func creneaux(_ detail: SondageDetailDTO) -> some View {
        GhostSection(titre: "Créneaux proposés") {
            VStack(alignment: .leading, spacing: 10) {
                ForEach(detail.options) { option in
                    HStack(spacing: 10) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(
                                verbatim: option.start_at.formatted(
                                    date: .abbreviated, time: .shortened)
                            )
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(Color.gcInk)
                            Text("\(option.votes) vote(s)")
                                .font(.caption)
                                .foregroundStyle(Color.gcMuted)
                        }
                        Spacer(minLength: 8)
                        if detail.finalized_option_id == option.id {
                            Label("Retenu", systemImage: "checkmark.circle.fill")
                                .font(.caption.weight(.medium))
                                .foregroundStyle(Color.gcAccentText)
                        } else if detail.finalized_option_id == nil {
                            Button("Retenir") { aRetenir = option }
                                .buttonStyle(SecondaryButtonStyle())
                                .accessibilityIdentifier("button.finalize")
                        }
                    }
                    if option.id != detail.options.last?.id { GhostDivider() }
                }
            }
            .padding(14)
        }
    }

    @ViewBuilder private func votants(_ detail: SondageDetailDTO) -> some View {
        if detail.voters.isEmpty {
            GhostSection(titre: "Votes") {
                Text("Personne n'a encore répondu.")
                    .font(.footnote)
                    .foregroundStyle(Color.gcMuted)
                    .padding(14)
            }
        } else {
            GhostSection(titre: "Votes") {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(detail.voters, id: \.email) { votant in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: votant.name.isEmpty ? votant.email : votant.name)
                                .font(.subheadline.weight(.medium))
                                .foregroundStyle(Color.gcInk)
                            Text("\(votant.option_ids.count) créneau(x) accepté(s)")
                                .font(.caption)
                                .foregroundStyle(Color.gcMuted)
                        }
                        if votant.email != detail.voters.last?.email { GhostDivider() }
                    }
                }
                .padding(14)
            }
        }
    }

    @ViewBuilder private func actions(_ detail: SondageDetailDTO) -> some View {
        if detail.finalized_option_id == nil {
            Button("Annuler le sondage", role: .destructive) {
                Task { await annuler() }
            }
            .buttonStyle(SecondaryButtonStyle())
            .accessibilityIdentifier("button.cancelPoll")
        }
    }

    private func charger() async {
        guard let api = session.api else { return }
        chargement = true
        defer { chargement = false }
        erreur = nil
        do {
            detail = try await Reglages(api: api).sondage(sondage.id)
        } catch {
            erreur = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    private func finaliser(_ option: OptionDeSondageDTO) async {
        guard let api = session.api else { return }
        erreur = nil
        do {
            detail = try await Reglages(api: api).finaliser(sondage.id, option: option.id)
            await apres()
        } catch {
            erreur = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    private func annuler() async {
        guard let api = session.api else { return }
        erreur = nil
        do {
            try await Reglages(api: api).annulerLeSondage(sondage.id)
            await apres()
            dismiss()
        } catch {
            erreur = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    private func presentation<T>(_ valeur: Binding<T?>) -> Binding<Bool> {
        Binding(
            get: { valeur.wrappedValue != nil },
            set: { presente in if !presente { valeur.wrappedValue = nil } })
    }
}
