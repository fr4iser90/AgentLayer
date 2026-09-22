import { useEffect, useRef } from "react";
import {
  MASCOTS,
  POSES,
  createRig,
  type MascotCharacterId,
  type MascotRig,
  type MascotState,
} from "./mascotArt";

export type { MascotCharacterId, MascotState } from "./mascotArt";
export { MASCOT_STATES, moodToState, agentTurnState } from "./mascotArt";

/**
 * One rAF loop drives every mounted mascot. A chat thread can easily show dozens
 * of avatars; per-instance loops would each cost a callback and a layout read,
 * and they would drift out of phase with each other.
 */
const subscribers = new Set<(t: number) => void>();
let frameHandle = 0;

function pump(ts: number) {
  const t = ts / 1000;
  subscribers.forEach((fn) => fn(t));
  frameHandle = requestAnimationFrame(pump);
}

function subscribe(fn: (t: number) => void): () => void {
  subscribers.add(fn);
  if (!frameHandle) frameHandle = requestAnimationFrame(pump);
  return () => {
    subscribers.delete(fn);
    if (!subscribers.size && frameHandle) {
      cancelAnimationFrame(frameHandle);
      frameHandle = 0;
    }
  };
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * Stable character for an identity string, so the same user always gets the same
 * mascot without anything having to be stored.
 */
export function pickCharacter(seed: string | null | undefined): MascotCharacterId {
  const ids = Object.keys(MASCOTS) as MascotCharacterId[];
  if (!seed) return ids[0];
  let h = 2166136261;
  for (let i = 0; i < seed.length; i += 1) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ids[Math.abs(h) % ids.length];
}

export interface MascotProps {
  character?: MascotCharacterId;
  state?: MascotState;
  /** Rendered edge length in px. The art is a square 200x200 viewBox. */
  size?: number;
  /** False renders a single still frame — use for dense lists. */
  animated?: boolean;
  /** Follow the cursor with the pupils. */
  trackPointer?: boolean;
  className?: string;
  /** Overrides the character label for assistive tech. Pass null to hide entirely. */
  ariaLabel?: string | null;
}

export function Mascot({
  character = "pim",
  state = "idle",
  size = 32,
  animated = true,
  trackPointer = false,
  className,
  ariaLabel,
}: MascotProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const rigRef = useRef<MascotRig | null>(null);
  const poseRef = useRef<MascotState>(state);
  const pointerRef = useRef({ x: 0, y: 0 });

  poseRef.current = state;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const rig = createRig(MASCOTS[character], host);
    rigRef.current = rig;

    const reduced = prefersReducedMotion();
    // A fixed phase keeps the still frame expressive; t=0 would land on the
    // bottom of the bob cycle and flatten every pose.
    if (reduced || !animated) {
      rig.apply(POSES[poseRef.current], 0.35);
      return () => {
        rig.destroy();
        rigRef.current = null;
      };
    }

    const unsub = subscribe((t) => {
      rig.apply(POSES[poseRef.current] ?? POSES.idle, t, trackPointer ? pointerRef.current : undefined);
    });
    return () => {
      unsub();
      rig.destroy();
      rigRef.current = null;
    };
  }, [character, animated, trackPointer]);

  useEffect(() => {
    if (!trackPointer) return;
    const onMove = (e: PointerEvent) => {
      const host = hostRef.current;
      const rig = rigRef.current;
      if (!host || !rig) return;
      const r = host.getBoundingClientRect();
      if (!r.width) return;
      const dx = (e.clientX - (r.left + r.width / 2)) / (r.width / 2);
      const dy = (e.clientY - (r.top + r.height / 2)) / (r.height / 2);
      pointerRef.current = {
        x: Math.max(-1, Math.min(1, dx)) * 4,
        y: Math.max(-1, Math.min(1, dy)) * 3,
      };
    };
    window.addEventListener("pointermove", onMove);
    return () => window.removeEventListener("pointermove", onMove);
  }, [trackPointer]);

  const label = ariaLabel === undefined ? MASCOTS[character].label : ariaLabel;

  return (
    <span
      ref={hostRef as unknown as React.RefObject<HTMLSpanElement>}
      className={className}
      style={{ display: "inline-flex", width: size, height: size, flexShrink: 0 }}
      role={label ? "img" : "presentation"}
      aria-label={label ?? undefined}
      aria-hidden={label ? undefined : true}
    />
  );
}
