/** Static still of the re-formed figure: no-WebGL fallback and the paint before 3D loads. */
export function HeroPoster() {
  return (
    <svg viewBox="0 0 400 400" className="h-full w-full" role="img" aria-label="Anonymised patient figure inside a protective ring">
      <defs>
        <radialGradient id="hp-glow" cx="50%" cy="48%" r="50%">
          <stop offset="0" stopColor="#2DD4BF" stopOpacity="0.28" />
          <stop offset="1" stopColor="#2DD4BF" stopOpacity="0" />
        </radialGradient>
        <pattern id="hp-dots" width="5" height="5" patternUnits="userSpaceOnUse">
          <circle cx="2.5" cy="2.5" r="1" fill="#2DD4BF" fillOpacity="0.75" />
        </pattern>
      </defs>
      <circle cx="200" cy="200" r="170" fill="url(#hp-glow)" />
      <g fill="url(#hp-dots)">
        <circle cx="200" cy="96" r="22" />
        <rect x="174" y="124" width="52" height="98" rx="24" />
        <rect x="150" y="128" width="16" height="84" rx="8" transform="rotate(8 158 128)" />
        <rect x="234" y="128" width="16" height="84" rx="8" transform="rotate(-8 242 128)" />
        <rect x="178" y="214" width="20" height="112" rx="10" />
        <rect x="202" y="214" width="20" height="112" rx="10" />
      </g>
      <ellipse cx="200" cy="184" rx="150" ry="34" fill="none" stroke="#67E8F9" strokeOpacity="0.45" strokeWidth="1.2" />
      <ellipse cx="200" cy="184" rx="150" ry="34" fill="none" stroke="#2DD4BF" strokeOpacity="0.08" strokeWidth="14" />
    </svg>
  );
}
