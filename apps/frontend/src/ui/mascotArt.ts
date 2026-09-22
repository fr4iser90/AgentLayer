/**
 * Mascot art + pose table.
 *
 * Deliberately data, not components. A character is a silhouette plus a fixed set
 * of part anchors; the renderer in createRig() knows nothing about which
 * character it is driving. Swapping in designer art means replacing a MASCOTS
 * entry — every pose keeps working as long as the part list is honoured.
 *
 * Coordinate space is a 200x200 viewBox. Part anchors (earAt / eyeAt / browAt /
 * mouthAt) are absolute in that space; ear shapes are drawn in local space and
 * mirrored, so one path serves both sides.
 */

export type MouthName =
  | "soft"
  | "smile"
  | "grin"
  | "flat"
  | "tight"
  | "o"
  | "frown"
  | "wavy"
  | "grit"
  | "openWide"
  | "smirk";

export type MascotCharacterId = "pim" | "volt" | "nimbus";

export interface EarPart {
  d: string;
  /** Filled with the body gradient. */
  fill?: boolean;
  /** Stroked with the rim colour instead of filled. */
  stroke?: boolean;
  w?: number;
}

export interface MascotDef {
  id: MascotCharacterId;
  label: string;
  pal: { a: string; b: string; rim: string; ink: string };
  body: string;
  earParts: EarPart[];
  earAt: Array<[number, number]>;
  mirror: [number, number];
  eyeType: "round" | "rect";
  eyeAt: Array<[number, number]>;
  eyeR: number;
  mouthAt: [number, number];
  browAt: Array<[number, number]>;
  bezel?: boolean;
}

export interface Pose {
  earL: number;
  earR: number;
  lift: number;
  eyeOpen: number;
  pupil: number;
  gazeX: number;
  gazeY: number;
  brow: number;
  mouth: MouthName;
  tilt: number;
  bob: number;
  squash: number;
  extras: string[];
  glow: number;
  spd: number;
  wink: boolean;
  spiral: boolean;
  trackHard: boolean;
}

const POSE_DEFAULTS: Pose = {
  earL: -6,
  earR: 6,
  lift: 0,
  eyeOpen: 1,
  pupil: 1,
  gazeX: 0,
  gazeY: 0,
  brow: 0,
  mouth: "smile",
  tilt: 0,
  bob: 0.5,
  squash: 1,
  extras: [],
  glow: 0.1,
  spd: 1,
  wink: false,
  spiral: false,
  trackHard: false,
};

const pose = (o: Partial<Pose>): Pose => ({ ...POSE_DEFAULTS, ...o });

export const MASCOTS: Record<MascotCharacterId, MascotDef> = {
  pim: {
    id: "pim",
    label: "Pim",
    pal: { a: "#2DD4BF", b: "#0F766E", rim: "#5EEAD4", ink: "#04211F" },
    body: "M100,38 C141,38 162,66 162,102 C162,142 136,166 100,166 C64,166 38,142 38,102 C38,66 59,38 100,38 Z",
    earParts: [
      { d: "M0,-2 C13,-6 21,-27 18,-46 C16,-57 6,-59 1,-50 C-7,-37 -9,-18 0,-2 Z", fill: true },
    ],
    earAt: [
      [68, 60],
      [132, 60],
    ],
    mirror: [-1, 1],
    eyeType: "round",
    eyeAt: [
      [80, 104],
      [120, 104],
    ],
    eyeR: 14,
    mouthAt: [100, 138],
    browAt: [
      [80, 82],
      [120, 82],
    ],
  },

  volt: {
    id: "volt",
    label: "Volt",
    pal: { a: "#A78BFA", b: "#5B21B6", rim: "#C4B5FD", ink: "#1A1030" },
    body: "M52,52 Q52,34 72,34 L128,34 Q148,34 148,52 L148,138 Q148,162 124,162 L76,162 Q52,162 52,138 Z",
    earParts: [
      { d: "M0,0 C5,-11 -4,-21 0,-31", stroke: true, w: 5 },
      { d: "M0,-31 A8,8 0 1,1 -0.2,-31 Z", fill: true },
    ],
    earAt: [
      [74, 38],
      [126, 38],
    ],
    mirror: [-1, 1],
    eyeType: "rect",
    eyeAt: [
      [80, 100],
      [120, 100],
    ],
    eyeR: 15,
    mouthAt: [100, 140],
    browAt: [
      [80, 78],
      [120, 78],
    ],
    bezel: true,
  },

  nimbus: {
    id: "nimbus",
    label: "Nimbus",
    pal: { a: "#93C5FD", b: "#1E40AF", rim: "#DBEAFE", ink: "#0A1F38" },
    body: "M62,86 C58,58 84,42 104,52 C118,34 152,44 148,72 C170,76 172,112 148,120 C152,148 118,162 100,148 C76,166 44,150 50,122 C28,114 34,84 62,86 Z",
    earParts: [
      { d: "M0,2 C12,2 19,-8 17,-17 C15,-27 4,-31 -4,-23 C-12,-15 -10,2 0,2 Z", fill: true },
    ],
    earAt: [
      [76, 58],
      [124, 58],
    ],
    mirror: [-1, 1],
    eyeType: "round",
    eyeAt: [
      [84, 102],
      [118, 102],
    ],
    eyeR: 13,
    mouthAt: [101, 134],
    browAt: [
      [84, 82],
      [118, 82],
    ],
  },
};

export const MOUTHS: Record<MouthName, string> = {
  soft: "M-14,0 Q0,9 14,0",
  smile: "M-20,0 Q0,15 20,0",
  grin: "M-23,-2 Q0,22 23,-2",
  flat: "M-16,0 L16,0",
  tight: "M-13,2 Q0,6 13,-1",
  o: "M-10,-4 Q0,15 10,-4 Q0,-15 -10,-4 Z",
  frown: "M-18,7 Q0,-9 18,7",
  wavy: "M-19,2 Q-9,-7 0,2 Q9,11 19,2",
  grit: "M-19,-5 L19,-5 M-19,6 L19,6 M-11,-5 L-11,6 M-3,-5 L-3,6 M5,-5 L5,6",
  openWide: "M-16,-6 Q0,26 16,-6 Q0,-18 -16,-6 Z",
  smirk: "M-17,3 Q-3,13 17,-4",
};

/** Open mouths read as a hole, so they get filled rather than stroked. */
const FILLED_MOUTHS = new Set<MouthName>(["o", "openWide"]);

export const POSES = {
  idle: pose({ mouth: "soft" }),
  happy: pose({ mouth: "grin", eyeOpen: 0.72, earL: -18, earR: 18, lift: -3, glow: 0.24, bob: 1.0 }),
  excited: pose({
    mouth: "openWide",
    eyeOpen: 1.15,
    pupil: 1.15,
    earL: -26,
    earR: 26,
    lift: -6,
    bob: 1.8,
    glow: 0.4,
    extras: ["sparkle"],
    spd: 1.5,
  }),
  curious: pose({ tilt: -9, earL: -24, earR: 2, lift: -3, eyeOpen: 1.1, gazeX: 0.35, mouth: "flat", brow: 0.35 }),
  thinking: pose({ eyeOpen: 0.8, gazeY: -0.55, mouth: "o", earL: 4, earR: -10, tilt: 6, bob: 0.25, extras: ["think"], spd: 0.7 }),
  working: pose({ eyeOpen: 0.7, gazeY: 0.35, mouth: "grit", earL: 10, earR: 10, lift: 2, bob: 0.8, spd: 1.35, glow: 0.18 }),
  focused: pose({ eyeOpen: 0.45, gazeY: 0.2, mouth: "flat", earL: 16, earR: 16, lift: 3, bob: 0.2, brow: -0.45, glow: 0.14 }),
  surprised: pose({ eyeOpen: 1.35, pupil: 0.7, mouth: "o", earL: -30, earR: 30, lift: -8, squash: 1.12, brow: 0.8, glow: 0.3 }),
  sleeping: pose({ eyeOpen: 0, mouth: "flat", earL: 18, earR: 18, lift: 5, bob: 0.18, squash: 0.95, extras: ["zzz"], spd: 0.45, glow: 0.05 }),
  wink: pose({ mouth: "grin", eyeOpen: 0.85, brow: 0.25, tilt: -5, earL: -16, earR: 8, wink: true }),
  confused: pose({ eyeOpen: 0.95, mouth: "wavy", tilt: 12, earL: -20, earR: 14, brow: 0.15, extras: ["question"], bob: 0.35 }),
  sad: pose({ eyeOpen: 0.55, mouth: "frown", earL: 22, earR: 22, lift: 7, bob: 0.2, glow: 0.05, gazeY: 0.3 }),
  love: pose({ mouth: "smile", eyeOpen: 0.85, earL: -18, earR: 18, lift: -3, glow: 0.35, extras: ["heart"], spd: 0.85 }),
  celebrating: pose({
    mouth: "openWide",
    eyeOpen: 1.1,
    earL: -32,
    earR: 32,
    lift: -9,
    bob: 2.1,
    glow: 0.5,
    extras: ["confetti", "sparkle"],
    spd: 1.6,
  }),
  creative: pose({ mouth: "smile", eyeOpen: 1, earL: -20, earR: 6, glow: 0.32, extras: ["note", "sparkle"], tilt: -4, spd: 0.95 }),
  awkward: pose({ mouth: "tight", eyeOpen: 0.9, gazeX: 0.5, earL: 14, earR: 18, lift: 2, extras: ["sweat"], tilt: 7, bob: 0.3 }),
  annoyed: pose({ mouth: "grit", eyeOpen: 0.6, brow: -0.9, earL: 22, earR: 22, lift: 5, glow: 0.22, spd: 1.15 }),
  gloomy: pose({ eyeOpen: 0.4, mouth: "frown", earL: 26, earR: 26, lift: 9, bob: 0.12, glow: 0.03, extras: ["rain"], spd: 0.4 }),
  dizzy: pose({ mouth: "wavy", earL: -14, earR: 20, bob: 0.5, extras: ["stars"], spd: 0.8, spiral: true }),
  starstruck: pose({ mouth: "openWide", eyeOpen: 1.15, gazeY: -0.45, earL: -22, earR: 22, lift: -5, glow: 0.45, extras: ["starEyes", "sparkle"] }),
  crying: pose({ eyeOpen: 0.5, mouth: "frown", earL: 28, earR: 28, lift: 10, glow: 0.06, extras: ["tears"], spd: 0.7, gazeY: 0.4 }),
  overheated: pose({ mouth: "grit", eyeOpen: 0.75, brow: -0.5, earL: 18, earR: 18, lift: 3, extras: ["steam", "sweat"], glow: 0.42, squash: 0.94, spd: 1.5 }),
  firedUp: pose({ mouth: "grit", eyeOpen: 0.9, brow: -0.6, earL: -18, earR: -18, lift: -5, glow: 0.6, extras: ["flame"], spd: 1.75 }),
  powering: pose({ mouth: "o", eyeOpen: 1.05, pupil: 1.25, earL: -10, earR: 10, lift: -4, glow: 0.72, extras: ["ring"], spd: 1.3 }),
  shocked: pose({ eyeOpen: 1.45, pupil: 0.45, mouth: "openWide", earL: 24, earR: 24, lift: 4, squash: 1.16, brow: 0.9, glow: 0.35 }),
  smug: pose({ eyeOpen: 0.5, mouth: "smirk", brow: 0.15, earL: -4, earR: 12, tilt: -4, bob: 0.3, gazeX: -0.25 }),
  deadpan: pose({ eyeOpen: 0.6, mouth: "flat", bob: 0, glow: 0.04, brow: 0, earL: 0, earR: 0 }),
  listening: pose({ eyeOpen: 1.15, mouth: "smile", earL: -22, earR: -16, lift: -4, brow: 0.3, bob: 0.45, trackHard: true }),
} satisfies Record<string, Pose>;

export type MascotState = keyof typeof POSES;

export const MASCOT_STATES = Object.keys(POSES) as MascotState[];

/** Three-axis mood -> discrete pose, mirroring the upstream mapping. */
export function moodToState(valence: number, arousal: number, attention: number): MascotState {
  if (arousal < 0.12) return valence < 0 ? "gloomy" : "sleeping";
  if (attention > 0.7) return valence > 0 ? "listening" : "focused";
  if (arousal > 0.8) return valence > 0 ? "excited" : "overheated";
  if (valence > 0.5) return arousal > 0.5 ? "happy" : "idle";
  if (valence < -0.4) return "sad";
  if (arousal > 0.55) return "working";
  return "idle";
}

/**
 * Agent turn -> pose. Kept out of the component so the mapping is testable on
 * its own and reusable by any surface that shows agent progress.
 */
export function agentTurnState(turn: {
  running: boolean;
  hasReasoning: boolean;
  cancelled: boolean;
}): MascotState {
  if (turn.cancelled) return "confused";
  if (!turn.running) return "happy";
  return turn.hasReasoning ? "thinking" : "working";
}

const NS = "http://www.w3.org/2000/svg";

function el<K extends keyof SVGElementTagNameMap>(
  name: K,
  attrs: Record<string, string | number>
): SVGElementTagNameMap[K] {
  const node = document.createElementNS(NS, name) as SVGElementTagNameMap[K];
  for (const k in attrs) node.setAttribute(k, String(attrs[k]));
  return node;
}

let rigSeq = 0;

interface EyeRig {
  group: SVGGElement;
  white: SVGElement;
  pupilGroup: SVGGElement;
  pupil: SVGCircleElement;
  lid: SVGRectElement;
  crease: SVGLineElement;
  shut: SVGPathElement;
  star: SVGPathElement;
  spiral: SVGPathElement;
}

/**
 * A live rig: the SVG plus handles on every part. Built imperatively because the
 * renderer was validated as a direct DOM driver — re-expressing it as a fully
 * declarative tree would mean re-validating 28 poses for no user-visible gain.
 */
export interface MascotRig {
  svg: SVGSVGElement;
  apply(pose: Pose, t: number, pointer?: { x: number; y: number }): void;
  destroy(): void;
}

export function createRig(def: MascotDef, host: Element): MascotRig {
  const uid = `m${(rigSeq += 1)}`;
  // The rig is decorative: the mounting element carries the accessible name.
  // Labelling both would expose two nested img roles for one mascot.
  const svg = el("svg", { viewBox: "0 0 200 200", "aria-hidden": "true", focusable: "false" });
  const defs = el("defs", {});

  // userSpaceOnUse so body, ears and eyelids all sample the SAME gradient at the
  // same coordinates — a closed lid then disappears into the head instead of
  // reading as a patch of the wrong colour.
  const bodyGrad = el("radialGradient", {
    id: `${uid}-g`,
    gradientUnits: "userSpaceOnUse",
    cx: 76,
    cy: 62,
    r: 152,
  });
  bodyGrad.appendChild(el("stop", { offset: "0%", "stop-color": def.pal.rim, "stop-opacity": 0.95 }));
  bodyGrad.appendChild(el("stop", { offset: "46%", "stop-color": def.pal.a, "stop-opacity": 0.86 }));
  bodyGrad.appendChild(el("stop", { offset: "100%", "stop-color": def.pal.b, "stop-opacity": 0.96 }));
  defs.appendChild(bodyGrad);

  // Halo: strongest just outside the head, fading to nothing at the rim.
  const halo = el("radialGradient", {
    id: `${uid}-halo`,
    gradientUnits: "userSpaceOnUse",
    cx: 100,
    cy: 104,
    r: 100,
  });
  halo.appendChild(el("stop", { offset: "0%", "stop-color": def.pal.rim, "stop-opacity": 0.3 }));
  halo.appendChild(el("stop", { offset: "62%", "stop-color": def.pal.rim, "stop-opacity": 0.22 }));
  halo.appendChild(el("stop", { offset: "82%", "stop-color": def.pal.rim, "stop-opacity": 0.07 }));
  halo.appendChild(el("stop", { offset: "100%", "stop-color": def.pal.rim, "stop-opacity": 0 }));
  defs.appendChild(halo);
  svg.appendChild(defs);

  const aura = el("circle", { cx: 100, cy: 104, r: 100, fill: `url(#${uid}-halo)`, opacity: 0 });
  svg.appendChild(aura);
  const root = el("g", {});
  svg.appendChild(root);

  const earRot: SVGGElement[] = [];
  const earLift: SVGGElement[] = [];
  const ears = el("g", {});
  def.earAt.forEach((p) => {
    const lift = el("g", { transform: `translate(${p[0]},${p[1]})` });
    const rot = el("g", {});
    const mirror = el("g", { transform: `scale(${def.mirror[0]},${def.mirror[1]})` });
    def.earParts.forEach((part) => {
      mirror.appendChild(
        el("path",
          part.stroke
            ? { d: part.d, fill: "none", stroke: def.pal.rim, "stroke-width": part.w ?? 4, "stroke-linecap": "round" }
            : { d: part.d, fill: `url(#${uid}-g)`, stroke: def.pal.rim, "stroke-width": 2, "stroke-opacity": 0.7 }
        )
      );
    });
    rot.appendChild(mirror);
    lift.appendChild(rot);
    ears.appendChild(lift);
    earRot.push(rot);
    earLift.push(lift);
  });
  root.appendChild(ears);

  const bodyG = el("g", {});
  bodyG.appendChild(
    el("path", { d: def.body, fill: `url(#${uid}-g)`, stroke: def.pal.rim, "stroke-width": 2.2, "stroke-opacity": 0.85 })
  );
  if (def.bezel) {
    bodyG.appendChild(
      el("rect", {
        x: 62,
        y: 64,
        width: 76,
        height: 78,
        rx: 13,
        fill: def.pal.ink,
        "fill-opacity": 0.28,
        stroke: def.pal.rim,
        "stroke-width": 1.2,
        "stroke-opacity": 0.5,
      })
    );
  }
  root.appendChild(bodyG);

  const face = el("g", {});
  const eyes: EyeRig[] = def.eyeAt.map((p, si) => {
    const side = si === 0 ? "L" : "R";
    const R = def.eyeR;
    const clipId = `${uid}-clip-${side}`;
    const clip = el("clipPath", { id: clipId });
    // Local coordinates: the clip is consumed by a <g> nested inside the already
    // translated eye group, so centring it on the eye's absolute position would
    // clip the whole eye away.
    clip.appendChild(
      def.eyeType === "rect"
        ? el("rect", { x: -R, y: -R, width: R * 2, height: R * 2, rx: 6 })
        : el("ellipse", { cx: 0, cy: 0, rx: R, ry: R })
    );
    defs.appendChild(clip);

    const group = el("g", { transform: `translate(${p[0]},${p[1]})` });
    const clipped = el("g", { "clip-path": `url(#${clipId})` });
    const white =
      def.eyeType === "rect"
        ? el("rect", { x: -R, y: -R, width: R * 2, height: R * 2, rx: 6, fill: "#F8FAFC" })
        : el("ellipse", { rx: R, ry: R, fill: "#F8FAFC" });
    const pupilGroup = el("g", {});
    const pupil = el("circle", { r: R * 0.46, fill: def.pal.ink });
    const shine = el("circle", { r: R * 0.17, fill: "#fff", opacity: 0.9, cx: -R * 0.18, cy: -R * 0.2 });
    pupilGroup.appendChild(pupil);
    pupilGroup.appendChild(shine);
    const star = el("path", {
      d: "M0,-10 L2.9,-3.1 10.5,-3.1 4.4,1.6 6.6,9.3 0,4.7 -6.6,9.3 -4.4,1.6 -10.5,-3.1 -2.9,-3.1 Z",
      fill: "#FDE68A",
      opacity: 0,
    });
    const spiral = el("path", {
      d: "M0,-9 a9,9 0 1,1 -0.1,0 M0,-5 a5,5 0 1,1 -0.1,0 M0,-1.7 a1.7,1.7 0 1,1 -0.1,0",
      fill: "none",
      stroke: def.pal.ink,
      "stroke-width": 1.7,
      opacity: 0,
    });
    const lid = el("rect", { x: -R - 2, y: -R - 2, width: R * 2 + 4, height: 0, fill: `url(#${uid}-g)` });
    const crease = el("line", {
      x1: -R * 0.85,
      x2: R * 0.85,
      y1: -R,
      y2: -R,
      stroke: def.pal.b,
      "stroke-width": 1.8,
      "stroke-linecap": "round",
      opacity: 0,
    });
    clipped.appendChild(white);
    clipped.appendChild(pupilGroup);
    clipped.appendChild(star);
    clipped.appendChild(spiral);
    clipped.appendChild(lid);
    clipped.appendChild(crease);
    group.appendChild(clipped);
    const shut = el("path", {
      d: `M${-R * 0.85},0 Q0,${R * 0.55} ${R * 0.85},0`,
      fill: "none",
      stroke: def.pal.ink,
      "stroke-width": 2.6,
      "stroke-linecap": "round",
      opacity: 0,
    });
    group.appendChild(shut);
    face.appendChild(group);
    return { group, white, pupilGroup, pupil, lid, crease, shut, star, spiral };
  });

  const browNodes: SVGPathElement[] = def.browAt.map((p) => {
    const b = el("path", {
      d: "M-10,0 L10,0",
      stroke: def.pal.ink,
      "stroke-width": 2.6,
      "stroke-linecap": "round",
      transform: `translate(${p[0]},${p[1]})`,
    });
    face.appendChild(b);
    return b;
  });

  const mouthGroup = el("g", { transform: `translate(${def.mouthAt[0]},${def.mouthAt[1]})` });
  const mouth = el("path", { fill: "none", stroke: def.pal.ink, "stroke-width": 3.2, "stroke-linecap": "round" });
  mouthGroup.appendChild(mouth);
  face.appendChild(mouthGroup);
  root.appendChild(face);

  const fx = el("g", {});
  root.appendChild(fx);

  host.appendChild(svg);

  function drawExtras(list: string[], t: number) {
    while (fx.firstChild) fx.removeChild(fx.firstChild);
    const put = <K extends keyof SVGElementTagNameMap>(name: K, attrs: Record<string, string | number>) => {
      const node = el(name, attrs);
      fx.appendChild(node);
      return node;
    };
    const wob = Math.sin(t * 3) * 3;

    if (list.includes("sparkle")) {
      const spots: Array<[number, number]> = [
        [46, 52],
        [158, 60],
        [150, 150],
        [40, 140],
      ];
      spots.forEach((p, i) => {
        const o = Math.sin(t * 2.4 + i) * 0.5 + 0.5;
        put("path", {
          d: "M0,-6 L1.8,-1.8 6,0 1.8,1.8 0,6 -1.8,1.8 -6,0 -1.8,-1.8 Z",
          fill: "#FDE68A",
          opacity: o * 0.9,
          transform: `translate(${p[0]},${p[1]}) scale(${0.7 + o * 0.6})`,
        });
      });
    }
    if (list.includes("sweat")) {
      put("path", {
        d: "M0,0 C4,6 6,11 0,14 C-6,11 -4,6 0,0 Z",
        fill: "#7DD3FC",
        transform: `translate(152,${62 + wob})`,
        opacity: 0.95,
      });
    }
    if (list.includes("steam")) {
      [0, 1].forEach((i) =>
        put("path", {
          d: "M0,0 q6,-8 0,-16 q-6,-8 0,-16",
          fill: "none",
          stroke: "#FCA5A5",
          "stroke-width": 3,
          "stroke-linecap": "round",
          opacity: 0.55 - i * 0.2,
          transform: `translate(${150 + i * 12},${44 - wob * 1.4})`,
        })
      );
    }
    if (list.includes("tears")) {
      [0, 1].forEach((s) => {
        const x = def.eyeAt[s][0];
        put("path", {
          d: "M0,0 C3,7 5,13 0,17 C-5,13 -3,7 0,0 Z",
          fill: "#93C5FD",
          transform: `translate(${x},${def.eyeAt[s][1] + 16 + ((t * 40 + s * 20) % 26)})`,
          opacity: 0.9,
        });
      });
    }
    if (list.includes("zzz")) {
      ["z", "Z", "z"].forEach((z, i) => {
        const node = put("text", {
          x: 162 + i * 12,
          y: 48 - i * 16 + wob * 0.6,
          fill: "#93C5FD",
          "font-size": 11 + i * 4,
          "font-family": "ui-monospace,monospace",
        });
        node.textContent = z;
      });
    }
    if (list.includes("think")) {
      [0, 1, 2].forEach((i) => {
        const o = Math.sin(t * 2.2 - i * 0.7) * 0.5 + 0.5;
        put("circle", { cx: 150 + i * 11, cy: 56 + i * 4, r: 2.6, fill: "#BAE6FD", opacity: o });
      });
    }
    if (list.includes("question")) {
      const node = put("text", {
        x: 152,
        y: 52 + wob,
        fill: "#FCD34D",
        "font-size": 26,
        "font-weight": "700",
        "font-family": "ui-sans-serif,sans-serif",
      });
      node.textContent = "?";
    }
    if (list.includes("heart")) {
      [0, 1, 2].forEach((i) =>
        put("path", {
          d: "M0,3 C-6,-3 -3,-9 0,-6 C3,-9 6,-3 0,3 Z",
          fill: "#F472B6",
          transform: `translate(${44 + i * 52},${58 + Math.sin(t * 1.6 + i) * 8}) scale(${1 + i * 0.2})`,
          opacity: 0.85,
        })
      );
    }
    if (list.includes("note")) {
      [0, 1].forEach((i) => {
        const node = put("text", {
          x: 150 - i * 118,
          y: 56 + i * 22 + wob,
          fill: "#A5B4FC",
          "font-size": 18 + i * 4,
        });
        node.textContent = "\u266A";
      });
    }
    if (list.includes("confetti")) {
      const colors = ["#F472B6", "#FCD34D", "#34D399", "#60A5FA", "#C084FC"];
      for (let i = 0; i < 12; i += 1) {
        const a = (i / 12) * Math.PI * 2;
        const r = 54 + Math.sin(t * 2 + i) * 10;
        const cx = 100 + Math.cos(a) * r;
        const cy = 100 + Math.sin(a) * r;
        put("rect", {
          x: cx - 2.5,
          y: cy - 2.5,
          width: 5,
          height: 5,
          fill: colors[i % colors.length],
          transform: `rotate(${((t * 120 + i * 40) % 360).toFixed(1)} ${cx.toFixed(1)} ${cy.toFixed(1)})`,
          opacity: 0.9,
        });
      }
    }
    if (list.includes("stars")) {
      for (let i = 0; i < 4; i += 1) {
        const a = t * 1.6 + i * (Math.PI / 2);
        put("path", {
          d: "M0,-5 L1.5,-1.5 5,0 1.5,1.5 0,5 -1.5,1.5 -5,0 -1.5,-1.5 Z",
          fill: "#FDE68A",
          transform: `translate(${100 + Math.cos(a) * 62},${96 + Math.sin(a) * 30})`,
          opacity: 0.85,
        });
      }
    }
    if (list.includes("flame")) {
      put("path", { d: "M100,182 C82,170 86,152 100,144 C114,152 118,170 100,182 Z", fill: "#F97316", opacity: 0.85 });
      put("path", { d: "M100,178 C90,170 92,158 100,154 C108,158 110,170 100,178 Z", fill: "#FDE047", opacity: 0.9 });
    }
    if (list.includes("rain")) {
      for (let i = 0; i < 5; i += 1) {
        put("line", {
          x1: 60 + i * 20,
          y1: 172,
          x2: 56 + i * 20,
          y2: 182,
          stroke: "#60A5FA",
          "stroke-width": 2,
          "stroke-linecap": "round",
          opacity: 0.5 + Math.sin(t * 3 + i) * 0.3,
        });
      }
    }
    if (list.includes("ring")) {
      [0, 1].forEach((i) => {
        const s = (t * 0.8 + i * 0.5) % 1;
        put("circle", {
          cx: 100,
          cy: 102,
          r: 40 + s * 52,
          fill: "none",
          stroke: def.pal.rim,
          "stroke-width": 2,
          opacity: (1 - s) * 0.7,
        });
      });
    }
  }

  function apply(p: Pose, t: number, pointer?: { x: number; y: number }) {
    const bob = Math.sin(t * 2.2 * p.spd) * 3 * p.bob;
    const sq = p.squash + Math.sin(t * 2.2 * p.spd) * 0.012 * p.bob;
    root.setAttribute(
      "transform",
      `translate(100,${(104 + bob).toFixed(2)}) rotate(${p.tilt}) scale(${(1 / Math.sqrt(sq)).toFixed(4)},${sq.toFixed(4)}) translate(-100,-104)`
    );
    aura.setAttribute("opacity", String(p.glow));

    earRot.forEach((rot, i) => {
      const flap = Math.sin(t * 2.2 * p.spd + i * 0.8) * 1.6 * p.bob;
      rot.setAttribute("transform", `rotate(${((i === 0 ? p.earL : p.earR) + flap).toFixed(2)})`);
      lift(i, p.lift);
    });

    eyes.forEach((eye, i) => {
      const R = def.eyeR;
      const isRight = i === 1;
      let open = Math.max(0, Math.min(1.6, p.eyeOpen));
      if (p.wink && isRight) open = 0.03;
      const shut = open < 0.1;
      const lidFrac = shut ? 1 : Math.max(0, 1 - open);

      eye.white.setAttribute("opacity", shut ? "0" : "1");
      eye.pupilGroup.setAttribute("opacity", shut ? "0" : "1");
      eye.shut.setAttribute("opacity", shut ? "1" : "0");
      const lidH = lidFrac * (R * 2 + 4);
      eye.lid.setAttribute("height", lidH.toFixed(2));
      const creaseY = -R - 2 + lidH;
      eye.crease.setAttribute("y1", creaseY.toFixed(2));
      eye.crease.setAttribute("y2", creaseY.toFixed(2));
      eye.crease.setAttribute("opacity", !shut && lidFrac > 0.06 ? "0.75" : "0");

      const reach = p.trackHard ? 7 : 5;
      const gx = p.gazeX * reach + (pointer ? pointer.x : 0);
      const gy = p.gazeY * 4 + (pointer ? pointer.y : 0);
      eye.pupilGroup.setAttribute("transform", `translate(${gx.toFixed(2)},${gy.toFixed(2)})`);
      eye.pupil.setAttribute("r", (R * 0.46 * p.pupil).toFixed(2));

      eye.star.setAttribute("opacity", p.extras.includes("starEyes") ? "1" : "0");
      eye.spiral.setAttribute("opacity", p.spiral ? String(0.75 + Math.sin(t * 4) * 0.25) : "0");
      if (p.spiral) eye.spiral.setAttribute("transform", `rotate(${(t * 90).toFixed(1)})`);

      const base = def.browAt[i];
      const liftPx = p.brow * 11;
      browNodes[i].setAttribute(
        "transform",
        `translate(${base[0]},${(base[1] - liftPx).toFixed(2)}) rotate(${((i === 0 ? 1 : -1) * p.brow * -12).toFixed(2)})`
      );
    });

    mouth.setAttribute("d", MOUTHS[p.mouth] ?? MOUTHS.smile);
    mouth.setAttribute("fill", FILLED_MOUTHS.has(p.mouth) ? def.pal.ink : "none");
    drawExtras(p.extras, t);
  }

  function lift(i: number, amount: number) {
    const base = def.earAt[i];
    earLift[i].setAttribute("transform", `translate(${base[0]},${base[1] + amount})`);
  }

  return {
    svg,
    apply,
    destroy() {
      if (svg.parentNode) svg.parentNode.removeChild(svg);
    },
  };
}
