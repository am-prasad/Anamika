import localFont from "next/font/local";

/** Self-hosted faces (SIL OFL), exposed as CSS variables on <html>. No network at build or run. */
export const display = localFont({
  src: "../fonts/BricolageGrotesque-var.woff2",
  variable: "--font-display-face",
  weight: "200 800",
  display: "swap",
});

export const sans = localFont({
  src: [
    { path: "../fonts/IBMPlexSans-400.woff2", weight: "400" },
    { path: "../fonts/IBMPlexSans-500.woff2", weight: "500" },
    { path: "../fonts/IBMPlexSans-600.woff2", weight: "600" },
  ],
  variable: "--font-sans-face",
  display: "swap",
});

export const mono = localFont({
  src: [
    { path: "../fonts/IBMPlexMono-400.woff2", weight: "400" },
    { path: "../fonts/IBMPlexMono-500.woff2", weight: "500" },
  ],
  variable: "--font-mono-face",
  display: "swap",
});

export const deva = localFont({
  src: [
    { path: "../fonts/NotoSansDevanagari-400.woff2", weight: "400" },
    { path: "../fonts/NotoSansDevanagari-500.woff2", weight: "500" },
    { path: "../fonts/NotoSansDevanagari-600.woff2", weight: "600" },
  ],
  variable: "--font-deva-face",
  display: "swap",
});

export const devaDisplay = localFont({
  src: "../fonts/TiroDevanagariHindi-400.woff2",
  variable: "--font-deva-display-face",
  display: "swap",
});

export const fontVariables = [display, sans, mono, deva, devaDisplay].map((f) => f.variable).join(" ");
