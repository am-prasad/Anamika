import type { Metadata, Viewport } from "next";

import { fontVariables } from "@/lib/fonts";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Anamika Console", template: "%s · Anamika" },
  description: "Visible to science, invisible to attackers. Privacy firewall for multilingual hospital records.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#050B14", colorScheme: "dark" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={fontVariables}>
      <body className="min-h-dvh antialiased">{children}</body>
    </html>
  );
}
