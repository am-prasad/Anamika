import { cn } from "@/lib/cn";

/** ANAMIKA / अनामिका wordmark with the shield-diamond glyph. */
export function Wordmark({ compact = false, className }: { compact?: boolean; className?: string }) {
  return (
    <span className={cn("flex items-center gap-3", className)}>
      <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden className="shrink-0">
        <defs>
          <linearGradient id="wm" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#2DD4BF" />
            <stop offset="1" stopColor="#67E8F9" />
          </linearGradient>
        </defs>
        <path d="M14 2 25 9v10l-11 7L3 19V9z" fill="none" stroke="url(#wm)" strokeWidth="1.5" />
        <circle cx="14" cy="14" r="3.2" fill="#2DD4BF" />
        <circle cx="14" cy="14" r="6.5" fill="none" stroke="#2DD4BF" strokeOpacity="0.35" />
      </svg>
      {!compact && (
        <span className="flex flex-col leading-none">
          <span className="font-display text-[17px] font-[800] tracking-[0.18em] text-text-hi">ANAMIKA</span>
          <span lang="hi" className="mt-1 font-deva-display text-[15px] text-text-mid">
            अनामिका
          </span>
        </span>
      )}
    </span>
  );
}
