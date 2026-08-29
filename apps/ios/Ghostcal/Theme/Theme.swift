// Charte visuelle de GhostCal, dérivée de celle de ghostpass.
//
// Les composants et la mécanique sont identiques — c'est la même suite, et une deuxième
// interprétation des mêmes règles finirait par diverger. Seule la couleur d'accent change :
// ghostcal est cyan (#00F0FF), ghostpass bleu, et la charte de la suite en fait foi
// (tools/brand/ghost_suite.py chez ghostpass).
//
// Le préfixe est `gc` et non `gp`, délibérément : le jour où du code circulerait d'un
// produit à l'autre, une couleur qui change de sens selon l'application serait un piège.

import SwiftUI

/// Le système visuel néon de la suite, partagé avec `ghostbit`, `ghostmon`, `ghostboard`,
/// `ghostauth` et `ghostcal`.
///
/// La structure est commune à tous les produits : une base sombre dérivée de Dracula, des
/// surfaces de verre fumé, et un halo coloré diffusé depuis le haut. Ce qui les distingue
/// est leur teinte néon, celle de leur logo — violet pour ghostbit, lime pour ghostmon,
/// orange pour ghostboard, menthe pour ghostauth, cyan pour ghostcal, jaune pour
/// ghostmail. Pour GhostCal, c'est le **bleu `#2E7DFF`**, seul créneau froid encore libre
/// et déjà celui de la marque.
///
/// Le néon n'est pas dans la couleur mais dans son rayonnement : deux halos superposés,
/// l'un serré et vif, l'autre large et discret. Voir `neon()`.
///
/// Les deux palettes existent, comme sur le web : le sombre est la teinte d'origine, le
/// clair une déclinaison de plein jour. On suit le réglage du système plutôt que d'imposer
/// l'un des deux.
extension Color {
    // ─── Base sombre commune à la suite (Dracula) ───

    /// Fond de page.
    static let gcBase = adaptative(sombre: 0x21222C, clair: 0xF5F8FC)
    /// Cartes et lignes.
    static let gcSurface = adaptative(sombre: 0x282A36, clair: 0xFFFFFF)
    /// Champs et surfaces imbriquées.
    static let gcSurface2 = adaptative(sombre: 0x323445, clair: 0xEEF3F9)
    /// Texte principal.
    static let gcInk = adaptative(sombre: 0xF8F8F2, clair: 0x0F1B2D)
    /// Texte secondaire.
    static let gcMuted = adaptative(sombre: 0x8B9CC8, clair: 0x5B6B82)

    // ─── Teinte de marque : bleu néon ───

    /// Accent plein : fonds de boutons, pastilles. Assez sombre pour porter du blanc.
    static let gcAccent = adaptative(sombre: 0x00F0FF, clair: 0x0E8FA8)
    /// Accent en texte ou en icône. Sur fond de nuit, le bleu plein manque de clarté :
    /// c'est la teinte haute de la marque qui prend le relais.
    static let gcAccentText = adaptative(sombre: 0x7FB2FF, clair: 0x1A4FCC)
    /// Ce qui se pose sur `gcAccent`.
    static let gcOnAccent = Color.white
    /// La teinte du halo. Fixe : un néon garde sa couleur, c'est ce qui le fait lire comme
    /// une source lumineuse plutôt que comme une ombre portée teintée.
    static let gcNeon = Color(rgb: 0x2E7DFF)

    static let gcBorder = adaptativeAlpha(sombre: (0xFFFFFF, 0.08), clair: (0x0F172A, 0.10))
    static let gcBorderStrong = adaptativeAlpha(sombre: (0xFFFFFF, 0.16), clair: (0x0F172A, 0.16))

    /// Sémantiques, reprises telles quelles de la base Dracula partagée.
    static let gcDanger = adaptative(sombre: 0xFF5555, clair: 0xD11F45)
    static let gcSuccess = adaptative(sombre: 0x50FA7B, clair: 0x15803D)

    /// Une teinte fixe, en hexadécimal. Sert aux couleurs qui ne dépendent pas du thème :
    /// les pastilles d'initiale, dont la palette est partagée avec la web app.
    init(rgb: Int) {
        self.init(UIColor(rgb: rgb, alpha: 1))
    }

    private static func adaptative(sombre: Int, clair: Int) -> Color {
        Color(
            UIColor { traits in
                UIColor(rgb: traits.userInterfaceStyle == .dark ? sombre : clair, alpha: 1)
            })
    }

    private static func adaptativeAlpha(
        sombre: (Int, CGFloat), clair: (Int, CGFloat)
    ) -> Color {
        Color(
            UIColor { traits in
                let (rgb, alpha) = traits.userInterfaceStyle == .dark ? sombre : clair
                return UIColor(rgb: rgb, alpha: alpha)
            })
    }
}

extension UIColor {
    fileprivate convenience init(rgb: Int, alpha: CGFloat) {
        self.init(
            red: CGFloat((rgb >> 16) & 0xFF) / 255,
            green: CGFloat((rgb >> 8) & 0xFF) / 255,
            blue: CGFloat(rgb & 0xFF) / 255,
            alpha: alpha)
    }
}

/// Mesures partagées. Les mêmes que sur le web : contrôles à 8, cartes à 16.
enum GC {
    static let radius: CGFloat = 12
    static let radiusCard: CGFloat = 16
    static let gap: CGFloat = 12
    static let padding: CGFloat = 16
    static let paddingCard: CGFloat = 24
}

/// Le halo néon de la suite : deux rayonnements superposés, l'un serré et vif, l'autre
/// large et diffus.
///
/// C'est la transposition exacte du `--brand-glow` partagé — `drop-shadow(0 0 8px …0.6)`
/// puis `drop-shadow(0 0 20px …0.35)`. Les deux comptent : un seul halo fait une tache
/// molle, tandis que la superposition d'un noyau net et d'une aura étalée est ce qui donne
/// l'impression d'une source de lumière. Le rayon est réduit en thème clair, où un néon
/// sur fond blanc devient une bavure.
struct Neon: ViewModifier {
    /// Multiplicateur d'intensité : 1 pour une marque, moins pour un détail.
    var force: Double = 1

    @Environment(\.colorScheme) private var schema

    func body(content: Content) -> some View {
        let echelle = schema == .dark ? force : force * 0.45
        return
            content
            .shadow(color: Color.gcNeon.opacity(0.60 * echelle), radius: 8 * echelle)
            .shadow(color: Color.gcNeon.opacity(0.35 * echelle), radius: 20 * echelle)
    }
}

extension View {
    /// Fait rayonner un élément dans la teinte de la marque.
    func neon(_ force: Double = 1) -> some View { modifier(Neon(force: force)) }
}

/// Le fond de l'application : nuit profonde et halo néon diffusé depuis le haut — la lueur
/// du fantôme, qui donne sa profondeur à l'ensemble sans rien coûter en lisibilité.
///
/// Le dégradé du fond est celui de la suite : quatre arrêts à 150°, teintés de la couleur
/// de marque, qui empêchent le noir d'être plat.
struct GhostBackground: View {
    @Environment(\.colorScheme) private var schema

    var body: some View {
        fond
            .overlay(alignment: .top) {
                RadialGradient(
                    colors: [Color.gcNeon.opacity(schema == .dark ? 0.26 : 0.12), .clear],
                    center: .top, startRadius: 0, endRadius: 520
                )
                .frame(height: 620)
                .offset(y: -140)
                .blur(radius: 40)
            }
            .ignoresSafeArea()
    }

    @ViewBuilder private var fond: some View {
        if schema == .dark {
            LinearGradient(
                colors: [
                    Color(rgb: 0x080D18), Color(rgb: 0x0A1220),
                    Color(rgb: 0x080F1A), Color(rgb: 0x090A10),
                ],
                startPoint: .top, endPoint: .bottom)
        } else {
            Color.gcBase
        }
    }
}

/// Carte de verre fumé : la surface translucide, bordée d'un filet clair.
struct GlassCard: ViewModifier {
    var padding: CGFloat = GC.paddingCard

    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(Color.gcSurface.opacity(0.65), in: rect)
            .overlay(rect.strokeBorder(Color.gcBorder, lineWidth: 1))
            .background(.ultraThinMaterial, in: rect)
    }

    private var rect: RoundedRectangle { RoundedRectangle(cornerRadius: GC.radiusCard) }
}

extension View {
    func glassCard(padding: CGFloat = GC.paddingCard) -> some View {
        modifier(GlassCard(padding: padding))
    }
}

/// Action principale : un bloc d'accent plein, pleine largeur.
struct PrimaryButtonStyle: ButtonStyle {
    var enabled = true

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.body, weight: .semibold))
            .foregroundStyle(Color.gcOnAccent)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(
                Color.gcAccent.opacity(enabled ? (configuration.isPressed ? 0.8 : 1) : 0.35),
                in: RoundedRectangle(cornerRadius: GC.radius)
            )
            // Seule l'action disponible rayonne. Faire luire un bouton inerte reviendrait
            // à appeler l'œil vers ce sur quoi on ne peut pas appuyer.
            .neon(enabled ? (configuration.isPressed ? 0.5 : 0.85) : 0)
            .contentShape(RoundedRectangle(cornerRadius: GC.radius))
    }
}

/// Action secondaire : le même bloc, mais creusé plutôt que plein.
struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.subheadline, weight: .medium))
            .foregroundStyle(Color.gcAccentText)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(
                Color.gcSurface2.opacity(configuration.isPressed ? 0.6 : 1),
                in: RoundedRectangle(cornerRadius: GC.radius)
            )
            .overlay(
                RoundedRectangle(cornerRadius: GC.radius)
                    .strokeBorder(Color.gcBorder, lineWidth: 1))
    }
}

/// Champ de saisie : surface creusée, bordure discrète, texte au repos lisible.
struct GhostFieldStyle: ViewModifier {
    func body(content: Content) -> some View {
        content
            .foregroundStyle(Color.gcInk)
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(Color.gcSurface2, in: RoundedRectangle(cornerRadius: GC.radius))
            .overlay(
                RoundedRectangle(cornerRadius: GC.radius)
                    .strokeBorder(Color.gcBorder, lineWidth: 1))
    }
}

extension View {
    func ghostField() -> some View { modifier(GhostFieldStyle()) }

    /// Intitulé de section : petites capitales espacées, comme sur le web.
    func sectionLabel() -> some View {
        font(.caption.weight(.semibold))
            .textCase(.uppercase)
            .kerning(0.6)
            .foregroundStyle(Color.gcMuted)
    }
}

// ─── Structures d'écran ───

/// Un écran de la suite : le fond de nuit, et un contenu qui défile par-dessus.
struct GhostScreen<Contenu: View>: View {
    var espacement: CGFloat = 22
    @ViewBuilder var contenu: () -> Contenu

    var body: some View {
        ZStack {
            GhostBackground()
            ScrollView {
                VStack(alignment: .leading, spacing: espacement) {
                    contenu()
                }
                .padding(.horizontal, 20)
                .padding(.top, 8)
                .padding(.bottom, 40)
                .frame(maxWidth: 560, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
            .scrollDismissesKeyboard(.interactively)
        }
    }
}

/// Une section : un intitulé en petites capitales, puis une carte qui réunit ses lignes.
struct GhostSection<Contenu: View>: View {
    // Clefs de traduction, pas des chaînes : ce qui s'écrit ici s'affiche, et doit donc
    // passer par le catalogue. Une `String` s'afficherait telle quelle, en français.
    var titre: LocalizedStringKey?
    var note: LocalizedStringKey?
    @ViewBuilder var contenu: () -> Contenu

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let titre { Text(titre).sectionLabel() }
            VStack(spacing: 0) { contenu() }
                .background(
                    Color.gcSurface.opacity(0.7),
                    in: RoundedRectangle(cornerRadius: GC.radiusCard)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: GC.radiusCard)
                        .strokeBorder(Color.gcBorder, lineWidth: 1))
            if let note {
                Text(note)
                    .font(.caption)
                    .foregroundStyle(Color.gcMuted)
                    .padding(.horizontal, 2)
            }
        }
    }
}

/// Un filet de séparation entre deux lignes d'une même carte.
struct GhostDivider: View {
    var body: some View {
        Rectangle()
            .fill(Color.gcBorder)
            .frame(height: 1)
            .padding(.leading, 14)
    }
}

/// Une ligne de consultation : un intitulé, une valeur, et ce qu'on peut en faire.
struct GhostRow<Actions: View>: View {
    let intitule: LocalizedStringKey
    /// Le contenu du coffre, jamais traduit : un mot de passe reste ce qu'il est.
    let valeur: String
    var monospace = false
    var estSecret = false
    @ViewBuilder var actions: () -> Actions

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(intitule)
                    .font(.caption)
                    .foregroundStyle(Color.gcMuted)
                // `.enabled` et `.disabled` sont deux types distincts : un ternaire ne
                // les unifie pas. Le modificateur ne porte donc que sur ce qui se copie.
                Group {
                    if estSecret {
                        Text(verbatim: valeur)
                    } else {
                        Text(verbatim: valeur).textSelection(.enabled)
                    }
                }
                .font(monospace ? .system(.body, design: .monospaced) : .body)
                .foregroundStyle(Color.gcInk)
                .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 8)
            HStack(spacing: 14) { actions() }
                .foregroundStyle(Color.gcAccentText)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }
}

/// Bouton d'action discret d'une ligne : une icône, une zone de frappe correcte.
struct GhostIconButton: View {
    let systemImage: String
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 16, weight: .medium))
                .frame(width: 30, height: 30)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundStyle(Color.gcAccentText)
    }
}

/// Ce que voit le sélecteur d'applications à la place du coffre : l'enseigne, rien d'autre.
///
/// iOS photographie l'écran quand l'application le quitte et garde cette vignette sur
/// disque. Un coffre déverrouillé s'y retrouverait en clair — noms de sites, identifiants —
/// visible d'un simple glissement, et lisible par qui inspecte le système de fichiers.
struct VoileDeConfidentialite: View {
    var body: some View {
        ZStack {
            GhostBackground()
            VStack(spacing: 12) {
                Image("LogoMark")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 56, height: 56)
                Text("GhostCal")
                    .font(.system(.headline, design: .rounded, weight: .semibold))
                    .foregroundStyle(Color.gcMuted)
            }
        }
        .ignoresSafeArea()
        .transition(.opacity)
        .accessibilityIdentifier("view.privacyVeil")
    }
}
