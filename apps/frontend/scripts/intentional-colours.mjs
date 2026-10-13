/**
 * Colours that stay raw, and the sentence that says why.
 *
 * A raw palette class in this tree means one of two things: nobody got to it,
 * or it is doing something a semantic token cannot do. The baselines record the
 * first kind — `{ file: [class, …] }`, re-recorded with `--update`, silent about
 * intent. This file records the second kind, and the difference is not
 * cosmetic: a baseline entry is allowed to grow stale, a justification is not.
 * Every key here must name a class that is actually in the tree, or the guard
 * run fails (see `unhitIntentionalKeys`).
 *
 * What a token cannot do: name one of fifteen peer entries in a catalogue. The
 * semantic tokens are four statuses (accent/success/warning/danger) plus the
 * three meanings Welle 4 named (unread/subagent/recording). A hue that indexes
 * a set of peers is not a status — `scan_queue` is not "a warning", it is the
 * fourth of twelve rows whose only distinction is hue. Mapping it onto
 * `warning` would make it indistinguishable from `permission` two rows away,
 * which is the opposite of what the surface is for.
 *
 * Three surfaces are of that kind:
 *   - `AgentActivityPanel.borderForKind` — 15 activity kinds, one hue each.
 *   - `RunCardBlock.borderForKind/bgForKind` — 4 run-card kinds.
 *   - `ModelCatalogSelect.CHIP_TONES` — 4 model capabilities.
 * Plus the dashboard canvas's highlight ring, where `accent` (selected) and
 * `unread` are already taken by the two other states of the same block.
 *
 * Matching drops variant prefixes: a justified `border-sky-500/45` also covers
 * `hover:border-sky-500/45`, because the decision being justified is the colour,
 * not the interaction. A new hue is never covered.
 */

/** file → class (no variant prefix) → reason. */
export const INTENTIONAL = {
  // 15 activity kinds in one rail. The hues are the only difference between the
  // rows, and the set already reuses a hue (goal, llm_queue and context_inject
  // are all amber) — proof that the hue is a limited alphabet here, not a
  // statement about severity.
  "src/features/chat/AgentActivityPanel.tsx": {
    "border-sky-500/50": "tool_start — einer von 15 Katalog-Tönen; plan (/45) ist derselbe Ton, also kein Status",
    "border-sky-500/45": "plan — siehe tool_start",
    "border-emerald-500/50": "tool_done — Nachbar von permission (amber) im selben Katalog; als success würde es sein Token mit einer Statusmeldung teilen, während agent.done bei emerald-600 bliebe",
    "border-emerald-600/40": "agent.done — bewusst eine Stufe dunkler als tool_done; eine Token-Stufe kann den Unterschied nicht tragen",
    "border-violet-500/45": "llm | think — violet-500 ist nicht `subagent` (#A78BFA = violet-400), der Live-Punkt trägt jetzt accent",
    "border-amber-500/45": "goal | llm_queue | context_inject — drei Katalogeinträge auf einem Ton; warning (permission) bleibt davon getrennt",
    "border-amber-500/50": "permission — der einzige Eintrag, der wirklich eine Warnung ist, aber als Katalogton neben goal/llm_queue gelesen wird",
    "border-teal-500/45": "todos — Teal hat kein Token; eine Abbildung auf success machte todos von tool_done ununterscheidbar",
    "border-orange-500/45": "deferred_wait | scan_queue — `unread` (#F0883E) bedeutet hier etwas anderes (ungelesen), warning ist permission",
  },
  // 4 run-card kinds. `subagent` became a token in block A precisely because it
  // names one meaning; the three remaining kinds are peers of each other, and
  // their fill/border pairs are what distinguishes a tool card from an index
  // card at a glance.
  "src/features/chat/RunCardBlock.tsx": {
    "border-sky-500/35": "Standard-Katalogton (tool) der Run-Karte — Fallback von borderForKind",
    "bg-sky-950/15": "derselbe Katalogton als Füllfläche zu border-sky-500/35",
    "border-violet-500/45": "index — Violet ist hier kein Unteragent; das subagent-Token (#A78BFA) wäre eine Verwechslung",
    "bg-violet-950/20": "index-Füllfläche zu border-violet-500/45",
    "border-amber-500/45": "compaction — Kompaktifizierung ist eine Kartenart, kein Warnzustand",
    "bg-amber-950/20": "compaction-Füllfläche zu border-amber-500/45",
  },
  // Model capabilities: four values of one field (text/vision/audio/context),
  // each rendered as border+fill+label in the same chip. Three of the four hues
  // collide with status tokens by accident of the palette; none of the four is a
  // status. A capability chip that reads as "success" would be a lie about a
  // model that happens to support images.
  "src/features/chat/ModelCatalogSelect.tsx": {
    "border-sky-400/30": "Capability text — Chip-Katalog; accent wäre ein Klick-State, der dasselbe Blau im selben Control trägt",
    "bg-sky-500/10": "text-Chip-Füllfläche",
    "text-sky-100": "text-Chip-Beschriftung auf bg-sky-500/10",
    "border-amber-400/35": "Capability audio — Chip-Katalog",
    "bg-amber-500/15": "audio-Chip-Füllfläche",
    "text-amber-100": "audio-Chip-Beschriftung auf bg-amber-500/15",
    "border-emerald-400/35": "Capability context — Chip-Katalog; success wäre eine Aussage über Qualität, nicht über Kontextlänge",
    "bg-emerald-500/15": "context-Chip-Füllfläche",
    "text-emerald-100": "context-Chip-Beschriftung auf bg-emerald-500/15",
    "border-violet-400/35": "Capability vision — der vierte Eintrag desselben Katalogs; er wäre auf halbem Weg zum Token als Ausnahme unlesbar",
    "bg-violet-500/15": "vision-Chip-Füllfläche",
    "text-violet-100": "vision-Chip-Beschriftung auf bg-violet-500/15",
  },
  // A canvas block has three simultaneous states, and two of the palette's
  // interactive hues are already spoken for: selected = accent, unread =
  // `unread`. The third state (highlighted by the canvas) needs its own hue.
  "src/features/dashboard/DashboardCanvasSurface.tsx": {
    "border-orange-500/50": "Hervorhebung, dritter Zustand neben selected (accent) und unread im selben Ausdruck",
  },
  "src/features/dashboard/DashboardGridInner.tsx": {
    "border-orange-500/50": "Hervorhebung, dritter Zustand neben selected (accent) und unread im selben Ausdruck",
  },
};

/** A class as it appears in source, without its variant chain. */
export function bareClassName(cls) {
  return cls.slice(cls.lastIndexOf(":") + 1);
}

/** The reason for one raw class in one file, or undefined if it has none. */
export function intentionalReason(rel, cls) {
  return INTENTIONAL[rel]?.[bareClassName(cls)];
}

/**
 * Every listed key whose class passes `matches` — each guard passes a test for
 * its own property (`border-`, `bg-`, `text-`), so a fill can never be counted
 * as a hit for a border and back.
 */
export function intentionalKeys(matches = () => true) {
  return Object.entries(INTENTIONAL).flatMap(([file, byClass]) =>
    Object.keys(byClass).filter(matches).map((cls) => `${file}::${cls}`)
  );
}

/**
 * Listed keys that no longer name anything in the tree, scoped to one guard.
 * A justification outliving its class is worse than no justification: the next
 * reader sees a reasoned allow-list and assumes the reasoning was reviewed
 * today.
 */
export function unhitIntentionalKeys(hit, matches = () => true) {
  return intentionalKeys(matches).filter((key) => !hit.has(key));
}