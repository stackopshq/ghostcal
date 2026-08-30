import type { Metadata } from "next";
import { headers } from "next/headers";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import ThemeToggle from "@/components/ThemeToggle";
import { I18nProvider } from "@/lib/i18n";
import "./globals.css";

// Set the theme before first paint to avoid a flash. Defaults to dark (the brand is dark-native).
const NO_FLASH_THEME = `(function(){try{var t=localStorage.getItem('gc_theme');document.documentElement.dataset.theme=(t==='light')?'light':'dark';}catch(e){document.documentElement.dataset.theme='dark';}})();`;

// Typography lives in `globals.css`, which imports the suite's `fonts.css`: Hanken
// Grotesk for the UI, JetBrains Mono for code, both self-hosted from `public/fonts/`.
// GhostCal used to pull Inter through `next/font/google` — served from our own origin,
// but a family none of the other seven products shared, and a build that had to reach
// Google to succeed.

// Origine publique du site, pour les URL absolues des aperçus de partage.
//
// GhostCal est multi-locataire : chaque client est servi sous son propre nom
// (`cal-<client>.ghostsuite.cloud`, voir `product_tenants.yml`). Il n'existe donc
// aucune URL que l'on puisse graver ici sans qu'elle soit fausse pour tous les
// autres locataires.
//
// Or un aperçu de partage exige une URL absolue : en relatif, aucun réseau social
// ne va chercher l'image, et il n'y a pas d'aperçu cassé, il n'y a pas d'aperçu du
// tout. On dérive donc l'origine de la requête courante, ce qui donne le bon nom
// chez chaque client sans configuration.
//
// `NEXT_PUBLIC_SITE_URL` reste une dérogation explicite, pour le jour où une valeur
// fixe est préférable (nom canonique, environnement de recette).
async function siteOrigin(): Promise<string> {
  const override = process.env.NEXT_PUBLIC_SITE_URL?.trim();
  if (override) return override.replace(/\/+$/, "");

  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "localhost:3000";
  // TLS est terminé en amont par le tunnel : la requête arrive en clair dans le
  // conteneur. Se fier au protocole vu localement mettrait des `http://` dans les
  // aperçus, que les réseaux sociaux refusent de charger depuis une page https.
  const isLocal = /^(localhost|127\.0\.0\.1|\[::1\])(:|$)/.test(host);
  const proto = h.get("x-forwarded-proto")?.split(",")[0].trim() ?? (isLocal ? "http" : "https");

  return `${proto}://${host}`;
}

const TITLE = "GhostCal · fast, correct scheduling";
const DESCRIPTION =
  "Pick a time in seconds. GhostCal is a fast, dark-mode-native scheduling tool.";

// Textes d'aperçu en français : la gamme s'adresse à des clients francophones.
// La description reste dans ce que le serveur sait réellement faire, les titres
// d'événements lui étant scellés (voir `ghostapp.yaml`).
const SHARE_TITLE = "GhostCal, planification rapide et fiable";
const SHARE_DESCRIPTION =
  "Choisissez un créneau en quelques secondes. Les titres de vos événements sont chiffrés : le serveur n'en connaît que les horaires.";

export async function generateMetadata(): Promise<Metadata> {
  const origin = await siteOrigin();

  return {
    // Sert de base aux URL relatives ci-dessous, que Next résout en absolu.
    metadataBase: new URL(origin),
    title: TITLE,
    description: DESCRIPTION,
    openGraph: {
      type: "website",
      siteName: "GhostCal",
      title: SHARE_TITLE,
      description: SHARE_DESCRIPTION,
      locale: "fr_FR",
      url: "/",
      images: [
        {
          url: "/og-image.png",
          width: 1200,
          height: 630,
          alt: "GhostCal",
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: SHARE_TITLE,
      description: SHARE_DESCRIPTION,
      images: ["/og-image.png"],
    },
  };
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html
      lang="en"
      data-theme="dark"
      suppressHydrationWarning
      className="h-full antialiased"
    >
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: NO_FLASH_THEME }} />
      </head>
      <body className="min-h-full flex flex-col">
        <I18nProvider>
          {children}
          <div className="fixed bottom-3 right-4 z-50 flex items-center gap-2 rounded-pill border border-border bg-surface/80 px-3 py-1 backdrop-blur">
            <ThemeToggle />
            <span className="text-border-strong">·</span>
            <LanguageSwitcher />
          </div>
        </I18nProvider>
      </body>
    </html>
  );
}
