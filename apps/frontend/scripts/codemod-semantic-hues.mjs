#!/usr/bin/env node
/**
 * Semantic-hue codemod (Welle 4, block A).
 *
 * `orange`, `indigo` and `rose` were each carrying several unrelated meanings,
 * which is why a hue -> token map would have been wrong here. The three hues
 * were polysemous:
 *
 *   orange  = an unread count            -> `unread`    (a thing nobody read yet)
 *           = a high-risk tool           -> `warning`   (a thing to be careful of)
 *           = a selected canvas block    -> stays raw   (a catalogue key, see below)
 *           = an activity-rail queue kind-> stays raw   (a catalogue key)
 *   indigo  = a delegated agent          -> `subagent`
 *           = a primary action / link    -> `accent`
 *   rose    = a live recording           -> `recording`
 *           = an error, a failure        -> `danger`
 *
 * So the mapping is stated per site rather than per hue. Every pair below was
 * read in context first. A pair that does not match exactly its expected number
 * of occurrences aborts the whole run — a codemod that silently skips is worse
 * than one that fails, because the leftover palette class then lands in the
 * ratchet baseline as if it had been reviewed.
 *
 * Deliberately NOT mapped, and why (these are decision 4's "catalogue keys": the
 * colour is an index into a set of peer kinds, not a status, so collapsing it
 * onto a semantic token would destroy the distinction the surface exists to
 * draw):
 *   - `border-orange-500/50 ring-2 ring-orange-500/40` in DashboardCanvasSurface
 *     and DashboardGridInner: the "highlighted" ring. `unread` would be a lie and
 *     `accent` collides with the neighbouring "selected" sky ring.
 *   - `border-orange-45` for `deferred_wait` / `scan_queue`, the `violet`/`teal`
 *     kind colours in AgentActivityPanel and the `violet` index kind in
 *     RunCardBlock.
 *   - `src/ui/ink-color-guard.test.ts`, which plants `text-rose-300` on purpose.
 *
 * Run: node scripts/codemod-semantic-hues.mjs [--dry]
 */
import { readFile, writeFile } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");

/** @type {{file: string, pairs: [string, string, number?]}[]} */
const PLAN = [
  // --- unread: a count nobody has read yet ------------------------------------
  // All five were `bg-orange-500 … text-black`. `text-black` is the one pure
  // black left in the app and fails the fill rule (white 2.7:1, black 5.3:1 on
  // this hue) — it moves onto the documented on-fill ink with the hue.
  {
    file: "components/NotificationBell.tsx",
    pairs: [
      ["rounded-pill bg-orange-500 px-tight text-meta font-semibold text-black",
       "rounded-pill bg-unread px-tight text-meta font-semibold text-ink-on-fill"],
    ],
  },
  {
    file: "features/dashboard/DashboardSidebarNav.tsx",
    pairs: [
      ["rounded-pill bg-orange-500 px-hair text-meta font-bold text-black align-middle",
       "rounded-pill bg-unread px-hair text-meta font-bold text-ink-on-fill align-middle"],
    ],
  },
  {
    file: "features/dashboard/DashboardOverviewPanel.tsx",
    pairs: [
      ["rounded-pill bg-orange-500 px-tight text-meta font-bold text-black align-middle",
       "rounded-pill bg-unread px-tight text-meta font-bold text-ink-on-fill align-middle"],
    ],
  },
  {
    file: "features/dashboard/AgentUpdateBadge.tsx",
    pairs: [
      ["rounded-pill bg-orange-500 px-tight text-meta font-bold leading-none text-black",
       "rounded-pill bg-unread px-tight text-meta font-bold leading-none text-ink-on-fill", 2],
    ],
  },
  {
    file: "features/dashboard/DashboardCanvasSurface.tsx",
    pairs: [["border-orange-500/25", "border-unread/25"]],
  },
  {
    file: "features/dashboard/DashboardGridInner.tsx",
    pairs: [["border-orange-500/25", "border-unread/25"]],
  },
  // The collision this token set exists to end: orange for a risk level while a
  // comment in the same file reserved orange for unread.
  {
    file: "pages/settings/ToolsSettings.tsx",
    pairs: [["bg-orange-500/20 px-snug py-hair text-meta text-orange-200",
             "bg-warning-subtle px-snug py-hair text-meta text-badge-warning"]],
  },

  // --- subagent: a delegated agent --------------------------------------------
  {
    file: "features/chat/AgentActivityPanel.tsx",
    pairs: [
      ['if (kind === "subagent_start") return "border-indigo-500/55";',
       'if (kind === "subagent_start") return "border-subagent/55";'],
      ['if (kind === "subagent_done") return "border-indigo-400/45";',
       'if (kind === "subagent_done") return "border-subagent/45";'],
      // The "Subagenten anzeigen" checkbox carries the identity of what it shows.
      ["rounded-tile border-line bg-field text-indigo-500",
       "rounded-tile border-line bg-field text-subagent"],
      ["text-meta text-indigo-300/90", "text-meta text-badge-subagent/90"],
    ],
  },
  {
    file: "features/chat/RunCardBlock.tsx",
    pairs: [
      // Only the `subagent` kind moves — it names something the palette now has a
      // meaning for. `index`, `compaction` and the default stay raw: peer entries
      // in a kind catalogue, not statuses.
      ['if (kind === "subagent") return "border-indigo-500/45";',
       'if (kind === "subagent") return "border-subagent/45";'],
      ['if (kind === "subagent") return "bg-indigo-950/25";',
       'if (kind === "subagent") return "bg-subagent-subtle";'],
      ["border-indigo-500/20", "border-subagent/20"],
      ["text-meta font-medium text-indigo-200/85", "text-meta font-medium text-badge-subagent/85"],
      ["text-indigo-200/50", "text-badge-subagent/50"],
      // The tool name inside a delegated run's expanded detail.
      ["text-indigo-300/80", "text-badge-subagent/80"],
      // Failures inside the same card were rose: those are errors, not a kind.
      ["text-rose-400/90", "text-danger/90", 2],
      ["text-rose-200/85", "text-badge-danger/85"],
    ],
  },

  // --- recording: a live capture ----------------------------------------------
  {
    file: "features/voice/VoiceMicButton.tsx",
    pairs: [
      ["border-rose-500/70 bg-rose-950/50 text-rose-100",
       "border-recording/70 bg-recording-subtle text-badge-recording"],
      ["border-rose-400/50", "border-recording/50"],
      ["border-rose-400/60 bg-rose-950 px-tight py-px text-meta font-bold uppercase leading-none tracking-wide text-rose-100",
       "border-recording/60 bg-recording px-tight py-px text-meta font-bold uppercase leading-none tracking-wide text-ink-on-fill"],
      ["bg-rose-400", "bg-recording", 2],
    ],
  },

  // --- rose that meant error, and indigo that meant primary -------------------
  {
    file: "features/voice/VoiceHandsFreeBar.tsx",
    pairs: [["text-rose-300", "text-danger"]],
  },
  {
    file: "features/chat/ConversationGoalPanels.tsx",
    pairs: [
      ["text-xs text-rose-200", "text-xs text-badge-danger"],
      ["text-xs text-rose-300/80", "text-xs text-danger/80", 2],
    ],
  },
  {
    file: "features/dashboard/DashboardBlocks.tsx",
    pairs: [["text-rose-400", "text-danger"]],
  },
  {
    file: "features/dashboard/DashboardBoardFilesPanel.tsx",
    pairs: [["text-xs text-rose-300", "text-xs text-danger"]],
  },
  {
    file: "features/admin/benchmarks/BenchmarkStatsPanel.tsx",
    pairs: [["text-rose-300", "text-danger"]],
  },
  {
    file: "features/admin/benchmarks/BenchmarkInsightsPanel.tsx",
    pairs: [
      // Specific before general: `text-rose-300` is a substring of the heading,
      // so mapping the hue first would consume both and leave the heading rule
      // matching nothing.
      ["text-xl font-semibold text-rose-300", "text-xl font-semibold text-danger"],
      ["text-rose-300", "text-danger"],
      ["bg-rose-500/70", "bg-danger/70"],
      ["bg-indigo-700/80 px-soft py-snug text-xs text-ink-primary hover:bg-indigo-600",
       "bg-accent/80 px-soft py-snug text-xs text-ink-on-fill hover:bg-accent-hover"],
    ],
  },
  {
    file: "features/admin/agentConfig/ExperimentDetailPanel.tsx",
    pairs: [
      ["text-rose-300 bg-rose-950/40 border-rose-500/30",
       "text-badge-danger bg-danger-subtle border-danger/30"],
      ["font-mono text-meta text-indigo-300", "font-mono text-meta text-badge-accent"],
      ["bg-indigo-700 px-soft py-snug text-xs text-ink-on-fill hover:bg-indigo-600",
       "bg-accent px-soft py-snug text-xs text-ink-on-fill hover:bg-accent-hover"],
    ],
  },
  {
    file: "pages/ProjectsPage.tsx",
    pairs: [
      ["border-rose-500/30 bg-rose-950/30 px-soft py-base text-sm text-rose-200",
       "border-danger/30 bg-danger-subtle px-soft py-base text-sm text-badge-danger"],
      ["text-xs text-rose-300", "text-xs text-danger"],
    ],
  },
  {
    file: "pages/org/OrgGrantsPage.tsx",
    pairs: [
      ["text-sm text-rose-300", "text-sm text-danger"],
      ["text-rose-300", "text-danger"],
    ],
  },
  {
    file: "pages/TasksPage.tsx",
    pairs: [
      ["border-indigo-500/50 bg-indigo-950/30", "border-accent/50 bg-accent-subtle"],
      ["border-indigo-500/35 bg-indigo-950/25 px-wide py-soft text-sm text-indigo-100/90",
       "border-accent/35 bg-accent-subtle px-wide py-soft text-sm text-badge-accent/90"],
      ["border-indigo-500/40 bg-indigo-500/15 px-wide py-base text-sm text-indigo-200",
       "border-accent/40 bg-accent-subtle px-wide py-base text-sm text-badge-accent"],
    ],
  },
  {
    file: "pages/settings/DelegateSettings.tsx",
    pairs: [
      ["text-indigo-300", "text-accent"],
      ["bg-indigo-600 px-wide py-base text-sm text-ink-on-fill hover:bg-indigo-500",
       "bg-accent px-wide py-base text-sm text-ink-on-fill hover:bg-accent-hover", 2],
    ],
  },
  {
    file: "pages/settings/AgentSettings.tsx",
    pairs: [["text-indigo-300", "text-accent"]],
  },
  {
    file: "pages/admin/AdminAgentTraces.tsx",
    pairs: [
      ["bg-indigo-500/20", "bg-accent-subtle"],
      ["text-xs text-indigo-200/90", "text-xs text-badge-accent/90"],
    ],
  },
  {
    file: "pages/admin/AdminAgents.tsx",
    pairs: [["text-rose-300", "text-danger", 2]],
  },
  {
    file: "pages/admin/interfaces/AdminInterfacesLlmSection.tsx",
    pairs: [
      ["bg-rose-500/25 text-rose-100", "bg-danger-subtle text-badge-danger"],
      ["border-rose-400/30 bg-rose-500/10 text-rose-100",
       "border-danger/30 bg-danger-subtle text-badge-danger"],
    ],
  },
  {
    file: "pages/admin/AdminBenchmarks.tsx",
    pairs: [
      ["border-rose-500/25 bg-rose-950/15", "border-danger/30 bg-danger-subtle"],
      ["text-sm font-medium text-rose-200", "text-sm font-medium text-badge-danger"],
      ["sticky top-0 bg-rose-950/80 text-ink-muted", "sticky top-0 bg-danger-subtle text-ink-muted"],
      ["py-tight pr-base align-top text-rose-200/90",
       "py-tight pr-base align-top text-badge-danger/90"],
      ["border-rose-500/40 bg-rose-950/30 px-soft py-snug text-xs font-medium text-rose-300 hover:bg-rose-950/50",
       "border-danger/40 bg-danger-subtle px-soft py-snug text-xs font-medium text-badge-danger hover:bg-danger/20"],
      ["text-rose-400/90 hover:bg-rose-950/40 hover:text-rose-300",
       "text-danger/90 hover:bg-danger/20 hover:text-badge-danger"],
      ["text-meta text-rose-300", "text-meta text-danger"],
    ],
  },
];

function countOccurrences(haystack, needle) {
  return haystack.split(needle).length - 1;
}

async function main() {
  const dry = process.argv.includes("--dry");
  const errors = [];
  const changed = new Map();

  for (const entry of PLAN) {
    const path = join(SRC, entry.file);
    let text = changed.get(entry.file)?.text ?? (await readFile(path, "utf8"));
    const pairs = [];

    for (const [from, to, expected = 1] of entry.pairs) {
      const n = countOccurrences(text, from);
      if (n !== expected) {
        errors.push(`${entry.file}: erwartet ${expected}×, gefunden ${n}× — ${from}`);
        continue;
      }
      // A replacement must not re-create a class the plan maps later on.
      if (countOccurrences(to, from) > 0 && text.includes(to)) {
        errors.push(`${entry.file}: "${to}" enthält "${from}" — Reihenfolge würde sich selbst fressen`);
        continue;
      }
      text = text.split(from).join(to);
      pairs.push([from, to, n]);
    }
    changed.set(entry.file, { text, pairs });
  }

  if (errors.length) {
    console.error(`[semantic-hues] Abbruch — ${errors.length} Mapping(s) passen nicht:`);
    for (const e of errors) console.error(`  ${e}`);
    console.error("[semantic-hues] Nichts geschrieben.");
    process.exit(1);
  }

  let moved = 0;
  for (const [file, { text, pairs }] of changed) {
    const n = pairs.reduce((a, p) => a + p[2], 0);
    moved += n;
    if (dry) {
      console.log(`  ${file}: ${n}`);
      continue;
    }
    await writeFile(join(SRC, file), text, "utf8");
    console.log(`  ${file}: ${n} Klasse(n) gemappt`);
  }
  console.log(
    `[semantic-hues] ${moved} Vorkommen in ${changed.size} Dateien ${dry ? "(dry-run, nichts geschrieben)" : "gemappt"}.`
  );
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});