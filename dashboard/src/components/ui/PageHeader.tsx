import { ExplainDrawer } from "./ExplainDrawer";

/** H1 + one line of what the screen proves + the Explain drawer. */
export function PageHeader({ eyebrow, title, lede, explainTitle, explain, aside }: {
  eyebrow: string;
  title: string;
  lede: React.ReactNode;
  explainTitle: string;
  explain: React.ReactNode;
  aside?: React.ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-6">
      <div className="max-w-[72ch] animate-rise">
        <p className="label text-teal-400/90">{eyebrow}</p>
        <h1 className="mt-2 font-display text-[40px] leading-[1.1] font-[700] tracking-[-0.01em] text-text-hi">{title}</h1>
        <p className="mt-3 text-[16px] leading-relaxed text-text-mid">{lede}</p>
      </div>
      <div className="flex items-center gap-3">
        {aside}
        <ExplainDrawer title={explainTitle}>{explain}</ExplainDrawer>
      </div>
    </div>
  );
}
