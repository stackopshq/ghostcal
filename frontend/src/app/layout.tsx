import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

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
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
