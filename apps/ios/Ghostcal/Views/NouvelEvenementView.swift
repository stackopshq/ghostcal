import SwiftUI

/// Créer un rendez-vous.
///
/// Le titre, la description et le lieu sont scellés avant de partir ; les heures non. Le
/// dire à l'écran plutôt que de le laisser deviner : quelqu'un qui choisit un gestionnaire
/// chiffré a le droit de savoir ce que son serveur apprend, et ce qu'il n'apprend pas.
struct NouvelEvenementView: View {
    @EnvironmentObject private var session: SessionStore
    @Environment(\.dismiss) private var dismiss

    let organisation: UUID?
    /// Rappelé à la fermeture pour que l'agenda se relise : un événement créé qui
    /// n'apparaît pas donne l'impression que rien ne s'est passé.
    let apresCreation: () async -> Void

    @State private var titre = ""
    @State private var lieu = ""
    @State private var description = ""
    @State private var debut = Date.prochaineDemiHeure()
    @State private var duree: TimeInterval = 3600
    @State private var journeeEntiere = false
    @State private var calendrier: UUID?
    @State private var calendriers: [CalendrierDTO] = []
    @State private var occupe = false
    @State private var erreur: String?

    private var vide: Bool { titre.trimmingCharacters(in: .whitespaces).isEmpty }

    var body: some View {
        NavigationStack {
            GhostScreen {
                VStack(alignment: .leading, spacing: 16) {
                    GhostSection(titre: "Rendez-vous") {
                        VStack(alignment: .leading, spacing: 12) {
                            champ("Titre") {
                                TextField(
                                    "", text: $titre,
                                    prompt: Text("Déjeuner, dentiste, revue…")
                                        .foregroundColor(Color.gcMuted.opacity(0.7))
                                )
                                .accessibilityIdentifier("field.title")
                            }
                            champ("Lieu") {
                                TextField(
                                    "", text: $lieu,
                                    prompt: Text("Facultatif")
                                        .foregroundColor(Color.gcMuted.opacity(0.7))
                                )
                                .accessibilityIdentifier("field.location")
                            }
                            champ("Notes") {
                                TextField(
                                    "", text: $description,
                                    prompt: Text("Facultatif")
                                        .foregroundColor(Color.gcMuted.opacity(0.7)),
                                    axis: .vertical
                                )
                                .lineLimit(2...5)
                                .accessibilityIdentifier("field.description")
                            }
                        }
                        .padding(14)
                    }

                    GhostSection(titre: "Quand") {
                        VStack(alignment: .leading, spacing: 12) {
                            Toggle("Journée entière", isOn: $journeeEntiere)
                                .tint(Color.gcAccent)
                                .accessibilityIdentifier("toggle.allDay")
                            DatePicker(
                                "Début", selection: $debut,
                                displayedComponents: journeeEntiere
                                    ? [.date] : [.date, .hourAndMinute]
                            )
                            .accessibilityIdentifier("picker.start")
                            if !journeeEntiere { selecteurDeDuree }
                        }
                        .foregroundStyle(Color.gcInk)
                        .padding(14)
                    }

                    if calendriers.count > 1 { selecteurDeCalendrier }
                    note
                    if let erreur { messageDErreur(erreur) }
                }
            }
            .navigationTitle("Nouveau rendez-vous")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Annuler") { dismiss() }
                        .foregroundStyle(Color.gcMuted)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Créer") { creer() }
                        .fontWeight(.semibold)
                        .foregroundStyle(vide || occupe ? Color.gcMuted : Color.gcAccentText)
                        .disabled(vide || occupe)
                        .accessibilityIdentifier("button.create")
                }
            }
        }
        .tint(Color.gcAccentText)
        .task { await chargerLesCalendriers() }
    }

    private var selecteurDeDuree: some View {
        Picker("Durée", selection: $duree) {
            Text("30 min").tag(TimeInterval(1800))
            Text("1 h").tag(TimeInterval(3600))
            Text("1 h 30").tag(TimeInterval(5400))
            Text("2 h").tag(TimeInterval(7200))
        }
        .pickerStyle(.segmented)
        .accessibilityIdentifier("picker.duration")
    }

    private var selecteurDeCalendrier: some View {
        GhostSection(titre: "Calendrier") {
            Picker(selection: $calendrier) {
                // Seuls ceux où l'on peut écrire. Proposer un calendrier en lecture seule
                // ferait échouer l'enregistrement une fois tout saisi — le pire moment
                // pour apprendre qu'on n'avait pas le droit.
                ForEach(calendriers.filter(\.inscriptible)) { calendrier in
                    Text(verbatim: calendrier.name).tag(Optional(calendrier.id))
                }
            } label: {
                EmptyView()
            }
            .pickerStyle(.menu)
            .tint(Color.gcAccentText)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(14)
            .accessibilityIdentifier("picker.calendar")
        }
    }

    private var note: some View {
        Label {
            Text(
                "Le titre, le lieu et les notes sont chiffrés sur cet appareil. Le serveur ne saura que la date et l'heure — de quoi vous rappeler le rendez-vous et marquer le créneau occupé."
            )
            .font(.footnote)
            .foregroundStyle(Color.gcMuted)
            .fixedSize(horizontal: false, vertical: true)
        } icon: {
            Image(systemName: "lock.fill").foregroundStyle(Color.gcAccentText)
        }
    }

    private func messageDErreur(_ texte: String) -> some View {
        Text(verbatim: texte)
            .font(.footnote)
            .foregroundStyle(Color.gcDanger)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("text.error")
    }

    private func champ<Contenu: View>(
        _ intitule: LocalizedStringKey, @ViewBuilder _ contenu: () -> Contenu
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(intitule).font(.caption).foregroundStyle(Color.gcMuted)
            contenu().foregroundStyle(Color.gcInk).ghostField()
        }
    }

    private func chargerLesCalendriers() async {
        guard let api = session.api, let auth = session.auth else { return }
        do {
            calendriers = try await Agenda(api: api, auth: auth).calendriers()
            calendrier =
                calendriers.first { $0.is_default && $0.inscriptible }?.id
                ?? calendriers.first(where: \.inscriptible)?.id
        } catch {
            erreur = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    private func creer() {
        guard let api = session.api, let auth = session.auth, let organisation,
            let calendrier
        else {
            erreur = String(localized: "Aucun calendrier où écrire.")
            return
        }
        occupe = true
        erreur = nil
        Task {
            defer { occupe = false }
            do {
                // Une journée entière couvre le jour civil complet dans le fuseau de
                // l'appareil : envoyer l'instant choisi tel quel ferait durer l'événement
                // de 14 h 30 à 14 h 30, ce que le serveur accepterait sans broncher.
                let calendrierCivil = Calendar.current
                let debutReel = journeeEntiere ? calendrierCivil.startOfDay(for: debut) : debut
                let finReelle =
                    journeeEntiere
                    ? calendrierCivil.date(byAdding: .day, value: 1, to: debutReel) ?? debutReel
                    : debut.addingTimeInterval(duree)

                try await Agenda(api: api, auth: auth).creerUnEvenement(
                    titre: titre.trimmingCharacters(in: .whitespaces),
                    description: description, lieu: lieu,
                    debut: debutReel, fin: finReelle, journeeEntiere: journeeEntiere,
                    calendrier: calendrier, organisation: organisation)
                await apresCreation()
                dismiss()
            } catch {
                erreur = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            }
        }
    }
}

extension Date {
    /// La prochaine demi-heure ronde.
    ///
    /// Proposer « maintenant » obligerait à corriger les minutes à chaque création : on ne
    /// prend pas rendez-vous à 14 h 37.
    static func prochaineDemiHeure(_ maintenant: Date = Date()) -> Date {
        let calendrier = Calendar.current
        let minutes = calendrier.component(.minute, from: maintenant)
        let ajout = minutes < 30 ? 30 - minutes : 60 - minutes
        let arrondi = calendrier.date(byAdding: .minute, value: ajout, to: maintenant) ?? maintenant
        return calendrier.date(bySetting: .second, value: 0, of: arrondi) ?? arrondi
    }
}
