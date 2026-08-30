import SwiftUI

/// Entrer dans GhostCal.
///
/// L'écran a trois visages, qui correspondent aux trois états de la session — et il faut
/// qu'ils soient distincts, sinon on redemande à quelqu'un ce qu'il vient de donner :
///
/// - **une session enregistrée** : la phrase seule, l'adresse et le compte étant connus ;
/// - **rien d'enregistré** : l'adresse, le compte, la phrase ;
/// - **connecté mais coffre fermé** : la phrase seule, avec la raison de l'échec
///   précédent affichée — c'est le cas le plus mal traité par les applications qui
///   confondent « pas authentifié » et « pas déchiffré ».
struct ConnexionView: View {
    @EnvironmentObject private var session: SessionStore

    @State private var phrase = ""
    @State private var parRecuperation = false
    @State private var changerDeCompte = false

    private var sessionReprise: Bool { session.sessionEnregistree && !changerDeCompte }

    var body: some View {
        GhostScreen {
            VStack(alignment: .leading, spacing: 18) {
                enseigne

                if case .coffreFerme(let raison) = session.etat {
                    coffreFerme(raison)
                } else if sessionReprise {
                    reprise
                } else {
                    formulaireComplet
                }

                if let erreur = session.erreur {
                    Text(verbatim: erreur)
                        .font(.footnote)
                        .foregroundStyle(Color.gcDanger)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("text.error")
                }

                bouton
                bascules
            }
            .padding(.top, 24)
        }
    }

    private var enseigne: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("GhostCal")
                .font(.system(.largeTitle, design: .rounded, weight: .bold))
                .foregroundStyle(Color.gcInk)
            Text("Votre agenda, chiffré de bout en bout.")
                .font(.subheadline)
                .foregroundStyle(Color.gcMuted)
        }
    }

    // ─── Les trois visages ───

    private var formulaireComplet: some View {
        VStack(alignment: .leading, spacing: 14) {
            champ("Serveur") {
                TextField(
                    "", text: $session.serveur,
                    // `verbatim` : une adresse ne se traduit pas. Le domaine est celui que
                    // la RFC 2606 réserve aux exemples — il ne résout nulle part, donc
                    // personne ne se connectera par mégarde à l'instance d'un tiers.
                    prompt: Text(verbatim: "https://ghostcal.example.com")
                        .foregroundColor(Color.gcMuted.opacity(0.7))
                )
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .keyboardType(.URL)
                .accessibilityIdentifier("field.server")
            }
            champ("Adresse e-mail") {
                TextField(
                    "", text: $session.email,
                    prompt: Text(verbatim: "vous@exemple.ch")
                        .foregroundColor(Color.gcMuted.opacity(0.7))
                )
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .keyboardType(.emailAddress)
                .accessibilityIdentifier("field.email")
            }
            champDePhrase
        }
    }

    private var reprise: some View {
        VStack(alignment: .leading, spacing: 14) {
            GhostRow(intitule: "Compte", valeur: session.email) {}
                .glassCard()
            champDePhrase
        }
    }

    private func coffreFerme(_ raison: String?) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            // Distinguer les deux échecs est tout l'intérêt de cet écran : ici la
            // connexion a réussi. Le dire évite de chercher du côté du mot de passe du
            // compte, qui est pourtant le bon.
            Text("Vous êtes connecté, mais le coffre n'est pas ouvert.")
                .font(.subheadline.weight(.medium))
                .foregroundStyle(Color.gcInk)
            if let raison, !raison.isEmpty {
                Text(verbatim: raison)
                    .font(.footnote)
                    .foregroundStyle(Color.gcMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            champDePhrase
        }
    }

    private var champDePhrase: some View {
        champ(parRecuperation ? "Phrase de récupération" : "Phrase de chiffrement") {
            SecureField(
                "", text: $phrase,
                prompt: Text("Votre phrase").foregroundColor(Color.gcMuted.opacity(0.7))
            )
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .submitLabel(.go)
            .onSubmit { entrer() }
            .accessibilityIdentifier("field.passphrase")
        }
    }

    // ─── Actions ───

    private var bouton: some View {
        Button(intituleDuBouton) { entrer() }
            .buttonStyle(
                PrimaryButtonStyle(
                    enabled: !phrase.trimmingCharacters(in: .whitespaces).isEmpty
                        && !session.occupe)
            )
            .disabled(phrase.trimmingCharacters(in: .whitespaces).isEmpty || session.occupe)
            .accessibilityIdentifier("button.submit")
    }

    private var intituleDuBouton: LocalizedStringKey {
        if case .coffreFerme = session.etat { return "Ouvrir le coffre" }
        return sessionReprise ? "Ouvrir le coffre" : "Se connecter"
    }

    private var bascules: some View {
        VStack(alignment: .leading, spacing: 10) {
            // La phrase de récupération sert quand on a perdu la sienne : le serveur range
            // une seconde enveloppe pour elle, et c'est le sel qui les distingue.
            Button(
                parRecuperation
                    ? "Utiliser ma phrase habituelle" : "J'utilise ma phrase de récupération"
            ) {
                parRecuperation.toggle()
            }
            .font(.footnote)
            .foregroundStyle(Color.gcAccentText)
            .accessibilityIdentifier("button.recovery")

            if sessionReprise {
                Button("Utiliser un autre compte") {
                    changerDeCompte = true
                    Task { await session.seDeconnecter() }
                }
                .font(.footnote)
                .foregroundStyle(Color.gcMuted)
                .accessibilityIdentifier("button.switchAccount")
            }
        }
    }

    private func entrer() {
        let saisie = phrase
        Task {
            if case .coffreFerme = session.etat {
                await session.deverrouiller(phrase: saisie, parRecuperation: parRecuperation)
            } else if sessionReprise {
                await session.reprendre(phrase: saisie, parRecuperation: parRecuperation)
            } else {
                await session.seConnecter(motDePasse: saisie)
            }
            if case .ouvert = session.etat { phrase = "" }
        }
    }

    private func champ<Contenu: View>(
        _ intitule: LocalizedStringKey, @ViewBuilder _ contenu: () -> Contenu
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(intitule)
                .font(.caption)
                .foregroundStyle(Color.gcMuted)
            contenu()
                .foregroundStyle(Color.gcInk)
                .ghostField()
        }
    }
}
