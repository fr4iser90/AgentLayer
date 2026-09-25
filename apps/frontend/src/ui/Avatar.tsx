/**
 * Identity avatar — always a mascot, never an initials circle.
 *
 * `ChatPage` painted hard-coded `"AL"` initials for the assistant. Three
 * unrelated avatar implementations existed and none of them used the character
 * system, which is the app's most distinctive asset and already wired:
 * `pickCharacter(seed)` gives a stable character per identity with no storage,
 * and `state` carries the agent's turn state straight onto the face.
 */
import { Mascot, pickCharacter, type MascotCharacterId, type MascotState } from "./Mascot";

export type AvatarKind = "agent" | "user" | "system";
export type AvatarSize = "sm" | "md" | "lg";

const SIZES: Record<AvatarSize, number> = { sm: 24, md: 32, lg: 48 };

export interface AvatarProps {
  kind?: AvatarKind;
  /** Stable identity: agent id, thread id, username. Same seed, same face. */
  seed: string | null | undefined;
  /** Override the derived character when the caller already knows it. */
  character?: MascotCharacterId;
  /** Agent turn state. Leave unset for a static identity. */
  state?: MascotState;
  size?: AvatarSize;
  /** Dense lists must pass `false` — one rAF loop per visible face is not free. */
  animated?: boolean;
  /** Screen-reader name. Required: a face without a name says nothing. */
  label: string;
  className?: string;
}

export function Avatar({
  kind = "agent",
  seed,
  character,
  state,
  size = "md",
  animated = true,
  label,
  className,
}: AvatarProps) {
  const resolved: MascotCharacterId =
    character ?? pickCharacter(seed ?? `${kind}:${label}`);
  return (
    <span
      className={["inline-flex shrink-0 items-center justify-center", className]
        .filter(Boolean)
        .join(" ")}
      role="img"
      aria-label={label}
    >
      <Mascot
        character={resolved}
        state={state ?? (kind === "system" ? "listening" : "idle")}
        size={SIZES[size]}
        animated={animated}
        trackPointer={false}
        ariaLabel={null}
      />
    </span>
  );
}