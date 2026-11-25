import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TrainerHub — one window for every single-player game trainer",
  description:
    "TrainerHub aggregates game trainers from multiple sources, searches them instantly in Chinese or English, and downloads, extracts and archives them into a browsable library. Windows first, MIT licensed.",
  keywords: [
    "game trainer",
    "single-player",
    "mods",
    "desktop app",
    "PySide6",
    "TrainerHub",
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
