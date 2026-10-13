/**
 * The one way an area says "there is nothing here".
 *
 * ~20 ad-hoc empty states were measured across the app, padding spread over
 * `py-6`/`py-10`/`p-8`, and not one of them used a mascot pose — while 28
 * poses already exist and are wired. The mascot is how this app identifies
 * itself, so an empty area with a generic grey icon is both a missed
 * characterisation and a second, quieter visual language.
 *
 * `pose` is semantic rather than a raw `MascotState` so an error and an empty
 * list cannot both end up on the shrugging face: they are different sentences.
 */
import type { ReactNode } from "react";
import { Mascot, type MascotCharacterId, type MascotState } from "./Mascot";

export type EmptyStatePose = "empty" | "noResults" | "error" | "denied" | "waiting";

const POSES: Record<EmptyStatePose, MascotState> = {
  empty: "idle",
  noResults: "curious",
  error: "overheated",
  denied: "gloomy",
  waiting: "thinking",
};

export interface EmptyStateProps {
  pose?: EmptyStatePose;
  /** Override the pose with an exact one when the semantic set is not enough. */
  mascot?: MascotState;
  character?: MascotCharacterId;
  title: string;
  hint?: string;
  action?: ReactNode;
  /** Dense lists must pass `false` — a rAF frame per mascot nobody looks at is pure cost. */
  animated?: boolean;
  size?: number;
  className?: string;
}

export function EmptyState({
  pose = "empty",
  mascot,
  character = "pim",
  title,
  hint,
  action,
  animated = true,
  size = 72,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={[
        "flex flex-col items-center justify-center gap-soft px-wide py-broad text-center",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <Mascot
        character={character}
        state={mascot ?? POSES[pose]}
        size={size}
        animated={animated}
        trackPointer={false}
      />
      <p className="text-title text-ink-primary">{title}</p>
      {hint ? <p className="max-w-measure text-body text-ink-muted">{hint}</p> : null}
      {action ? <div className="mt-soft">{action}</div> : null}
    </div>
  );
}