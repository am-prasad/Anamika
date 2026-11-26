import { cn } from "@/lib/cn";

type Props = React.HTMLAttributes<HTMLElement> & {
  level?: 1 | 2 | 3;
  interactive?: boolean;
  as?: "section" | "div" | "article" | "aside";
};

/** The one card. Level 1 tiles, 2 cards, 3 popovers; radius 20 outer. */
export function GlassCard({ level = 2, interactive, as: Tag = "section", className, ...rest }: Props) {
  return (
    <Tag
      className={cn(`glass-${level} rounded-[20px]`, interactive && "glass-interactive", className)}
      {...rest}
    />
  );
}
