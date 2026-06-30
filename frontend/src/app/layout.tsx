import type { Metadata } from "next";
import { Inter } from "next/font/google";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import ThemeToggle from "@/components/ThemeToggle";
import { I18nProvider } from "@/lib/i18n";
import "./globals.css";

// Set the theme before first paint to avoid a flash. Defaults to dark (the brand is dark-native).
const NO_FLASH_THEME = `(function(){try{var t=localStorage.getItem('gc_theme');document.documentElement.dataset.theme=(t==='light')?'light':'dark';}catch(e){document.documentElement.dataset.theme='dark';}})();`;

// Inter (SIL OFL) — matches the chosen typography (see docs/adr/0001).
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "GhostCal — fast, correct scheduling",
  description:
    "Pick a time in seconds. GhostCal is a fast, dark-mode-native scheduling tool.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      data-theme="dark"
      suppressHydrationWarning
      className={`${inter.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_THEME }} />
      </head>
      <body className="min-h-full flex flex-col">
        <I18nProvider>
          {children}
          <div className="fixed bottom-3 right-4 z-50 flex items-center gap-2 rounded-full border border-border bg-surface/80 px-3 py-1 backdrop-blur">
            <ThemeToggle />
            <span className="text-border-strong">·</span>
            <LanguageSwitcher />
          </div>
        </I18nProvider>
      </body>
    </html>
  );
}
