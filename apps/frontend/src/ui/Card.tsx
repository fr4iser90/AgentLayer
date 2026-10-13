import type { HTMLAttributes, ReactNode } from "react";

export type CardElevation = "card" | "raised" | "panel";
export type CardPadding = "none" | "snug" | "soft" | "wide" | "roomy";

// Elevation is the surface ladder, not a shadow: on a dark theme the hue-shifted
// step is what separates two planes. `raised` is for a card that is being
// interacted with, `panel` for chrome that sits beside content.
const ELEVATION: Record<CardElevation, string> = {
  card: "rounded-card border border-line bg-card shadow-card",
  raised: "rounded-card border border-line-strong bg-raised shadow-raised",
  panel: "rounded-sheet border border-line bg-panel shadow-panel",
};

const PADDING: Record<CardPadding, string> = {
  none: "",
  snug: "p-snug",
  soft: "p-soft",
  wide: "p-wide",
  roomy: "p-roomy",
};

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  elevation?: CardElevation;
  padding?: CardPadding;
  children?: ReactNode;
}

export function cardClasses(
  elevation: CardElevation = "card",
  padding: CardPadding = "wide",
  ...extra: Array<string | false | null | undefined>
): string {
  return [ELEVATION[elevation], PADDING[padding], ...extra].filter(Boolean).join(" ");
}

export function Card({
  elevation = "card",
  padding = "wide",
  className,
  children,
  ...rest
}: CardProps) {
  return (
    <div className={cardClasses(elevation, padding, className)} {...rest}>
      {children}
    </div>
  );
}