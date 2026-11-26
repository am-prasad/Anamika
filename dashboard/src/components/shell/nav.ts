import { Activity, HeartPulse, Network, Radar, ScanText, ShieldCheck, type LucideIcon } from "lucide-react";

/** The six screens, in demo order. */
export const NAV: { href: string; label: string; short: string; icon: LucideIcon }[] = [
  { href: "/overview", label: "Command Overview", short: "Overview", icon: Activity },
  { href: "/redaction", label: "Redaction Studio", short: "Redaction", icon: ScanText },
  { href: "/identity", label: "Identity Graph", short: "Identity", icon: Network },
  { href: "/attack", label: "Attack Simulator", short: "Attack", icon: Radar },
  { href: "/integrity", label: "Clinical Integrity", short: "Clinical", icon: HeartPulse },
  { href: "/audit", label: "Security & Audit", short: "Audit", icon: ShieldCheck },
];
