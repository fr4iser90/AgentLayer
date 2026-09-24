/**
 * Design tokens.
 *
 * Elevation is carried by hue-shifted surface steps, not by shadows: on a dark
 * theme a drop shadow barely registers, while a cool tint (B > R) makes two
 * adjacent panels separable where neutral blacks of similar lightness are not.
 * Every step below is >= 1.10:1 against the level it sits on, which is the
 * minimum that reads as a distinct plane without looking like a border.
 *
 * `surface-*` is kept as a compatibility alias over the new tokens so existing
 * call sites pick up the new palette without being edited.
 */

/** @type {import('tailwindcss').Config} */

// Elevation: canvas -> panel -> card -> raised
const CANVAS = "#0B0C0E"; // app background
const PANEL = "#15181D"; // chrome: header, footer, sidebars
const CARD = "#1E222A"; // content containers
const RAISED = "#2A2F39"; // hovered/active controls, popovers
const OVERLAY = "rgba(6, 7, 9, 0.72)"; // modal scrim

// Hairlines. Contrast against the level they outline is deliberately low: these
// separate, they do not decorate. `strong` is for focus-adjacent emphasis.
const LINE_SUBTLE = "#23282F";
const LINE_DEFAULT = "#2E343E";
const LINE_STRONG = "#3F4753";
const LINE_FOCUS = "#4C8DFF";

// Text. `faint` is 3.47:1 on card and therefore decorative-only — never for
// information a user has to read.
const TEXT_PRIMARY = "#E8EAED";
const TEXT_SECONDARY = "#B4BAC4";
const TEXT_MUTED = "#A3A9B4";
const TEXT_FAINT = "#6E7682";

const ACCENT = "#4C8DFF";
const SUCCESS = "#3FB950";
const WARNING = "#D29922";
const DANGER = "#F85149";
// Dark ink for text sitting on a saturated fill. White fails on all four fills
// (2.52–3.35:1); this passes at 5.94–7.89:1.
const ON_FILL = "#08090B";

// Form-field fill. Chosen to read as inset against every level a field can sit
// on: lighter than canvas (1.044:1), darker than panel (1.054:1) and card
// (1.176:1). A single alpha like the old bg-black/20 could not do that — it
// went invisible on canvas and muddy on card.
const FIELD = "#0F1218";
const FIELD_PLACEHOLDER = "#7B8390";

export default {
  // The guard tests plant violations on purpose (`z-[999]`, `bg-red-500`,
  // `max-w-6xl`) and must plant them in the exact form the guard reads. They
  // are not app code, though: with test files in this glob every one of those
  // classes is emitted into the shipped stylesheet, so a level the token scale
  // exists to make untypeable stays perfectly renderable.
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    "!./src/**/*.test.{js,ts,jsx,tsx}",
  ],
  theme: {
    // Stacking levels, named by what floats rather than by a number.
    //
    // Deliberately NOT inside `extend`. A top-level theme key replaces
    // Tailwind's default scale instead of adding to it, so `z-50` and `z-[100]`
    // stop generating any CSS at all. A guard can only report a raw level after
    // it has been typed and shipped; removing the scale makes it unrenderable.
    // Arbitrary values (`z-[7]`) cannot be removed this way — that is what
    // scripts/check-z-index.mjs is for.
    //
    // Measured from 45 call sites spread over nine values where the numbers had
    // stopped meaning anything: `z-50` carried both dropdown menus and
    // full-screen modal scrims, so a page-level menu could float over a dialog
    // that had just blocked the page; and one role — modal — used three
    // different numbers (`z-50`, `z-[80]`, `z-[100]`), leaving dialog-over-
    // dialog undefined.
    //
    // `tooltip` sits above `modal` on purpose. The tooltip is the only portaled
    // layer in the app (document.body); dialogs render in place and therefore
    // contain their own descendants' stacking. A dialog at 100 paints over a
    // tooltip at 60, so a tooltip anchored to a control inside a dialog would
    // be invisible — latent today, because no dialog contains one yet.
    //
    // `sheet` and `drawer` are deliberately NOT used here: `rounded-sheet` and
    // `max-w-drawer` already own those words at a different scale, and a word
    // that names a radius in one place must not name an elevation in another.
    // `overlay` IS reused from `bg-overlay`/`shadow-overlay` because all three
    // name the same thing — the floating scrim layer.
    zIndex: {
      auto: "auto", // rejoin normal flow, e.g. md:z-auto on a mobile-only layer

      // Above the content of its own container, never into the app's order:
      // a mic badge over its button, a sticky save bar, a veil over the composer.
      lift: "10",

      // The dashboard canvas's own chrome, floating over blocks but under every
      // menu: resize handles, a block's update badge, a canvas-level note.
      canvas: "20",

      // A popover anchored inside a panel and bounded by it: the thread menu in
      // the embedded dashboard chat, the model picker above the chat input.
      docked: "30",

      // App chrome that covers the page and stays under anything floating:
      // the collapsible sidebar's mobile scrim.
      chrome: "40",

      // Anchored popovers over the page: user menu, notification bell, nav
      // dropdown, model catalog select.
      menu: "50",

      // A sheet with its own scrim — the settings and detail drawers, anchored
      // right or bottom rather than centred.
      overlay: "80",

      // Dialog and lightbox: top of the app, containing everything inside it.
      modal: "100",

      // Top of the order. See the note above: a tooltip describes the control
      // under the cursor, including one inside an open dialog.
      tooltip: "120",
    },
    extend: {
      colors: {
        canvas: CANVAS,
        panel: PANEL,
        card: CARD,
        raised: RAISED,
        overlay: OVERLAY,

        field: {
          DEFAULT: FIELD,
          placeholder: FIELD_PLACEHOLDER,
        },

        // Hairlines: `border-line`, `border-line-subtle`, `divide-line`
        line: {
          DEFAULT: LINE_DEFAULT,
          subtle: LINE_SUBTLE,
          strong: LINE_STRONG,
          focus: LINE_FOCUS,
        },

        // Text tones: `text-ink-primary`, `text-ink-muted`, ...
        ink: {
          DEFAULT: TEXT_PRIMARY,
          primary: TEXT_PRIMARY,
          secondary: TEXT_SECONDARY,
          muted: TEXT_MUTED,
          faint: TEXT_FAINT,
          "on-fill": ON_FILL,
        },

        accent: {
          DEFAULT: ACCENT,
          hover: "#6BA1FF",
          press: "#3A76E0",
          subtle: "rgba(76, 141, 255, 0.15)",
        },

        success: {
          DEFAULT: SUCCESS,
          hover: "#5CD96D",
          subtle: "rgba(63, 185, 80, 0.15)",
        },
        warning: {
          DEFAULT: WARNING,
          hover: "#E3AC3B",
          subtle: "rgba(210, 153, 34, 0.16)",
        },
        danger: {
          DEFAULT: DANGER,
          hover: "#FF6B63",
          subtle: "rgba(248, 81, 73, 0.16)",
        },

        // Badge label tones. The raw semantic colours fail on their own 15-16%
        // tint (accent 4.03:1, danger 3.98:1), so badge text is lifted to
        // 6.63-8.19:1 against the composited chip.
        badge: {
          accent: "#9DC3FF",
          success: "#7EE78F",
          warning: "#F5C86E",
          danger: "#FF9C95",
        },

        // --- compatibility aliases (do not use in new code) ---
        // surface.DEFAULT and surface.raised were dropped once every fill moved
        // onto the ladder. surface.raised pointed at PANEL, so its name promised
        // a raised level while it painted the chrome colour — check-surface-
        // ladder.mjs keeps the fill aliases from coming back.
        surface: {
          border: LINE_DEFAULT,
          // Kept at roughly today's brightness: this token has ~1.2k call sites,
          // and the spec's 5.09:1 `muted` would dim all of them from 7.7:1.
          muted: TEXT_MUTED,
        },
      },

      // Five-step type scale. Replaces the ~600 one-off `text-[Npx]` sizes; the
      // floor is 11px, nothing smaller.
      fontSize: {
        display: ["20px", { lineHeight: "28px", fontWeight: "600", letterSpacing: "-0.01em" }],
        title: ["16px", { lineHeight: "24px", fontWeight: "600" }],
        body: ["14px", { lineHeight: "22px", fontWeight: "400" }],
        label: ["12px", { lineHeight: "16px", fontWeight: "500" }],
        meta: ["11px", { lineHeight: "14px", fontWeight: "400" }],
      },

      // Self-hosted, so the stack after the family name is the fallback that
      // paints during the swap window. Kept short and generic on purpose: the
      // faces are small enough to arrive fast, and a long stack of
      // metric-mismatched candidates is what makes a swap visible.
      fontFamily: {
        sans: [
          '"IBM Plex Sans"',
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          '"Segoe UI"',
          "Roboto",
          "sans-serif",
        ],
        mono: [
          '"IBM Plex Mono"',
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },

      // Spacing ramp, named by density role rather than by number. Numeric
      // names would have been a no-op rename: Tailwind's own scale is already
      // 4px-based, so `space-2` = 8px = `p-2`. Only semantic names make the
      // ramp project-owned and the guard able to tell an on-ramp step from an
      // off-ramp one.
      //
      // Measured from the app's 5248 spacing classes rather than invented:
      // 8px alone is 23.7 %, 4/8/12/16 together 62.1 %. The twelve steps
      // below cover every value that recurs; the six one-off values above
      // 48px are tolerated as guard baseline rather than named.
      //
      // Not a strict 4px grid, deliberately: hair (2px) and snug (6px) sit
      // between the multiples because dense rows need them. `firm` exists so
      // the Button primitive's sm/md/lg horizontal rhythm (10/12/16px)
      // survives the migration without moving a single pixel.
      //
      // `spacing` feeds p-*, m-*, gap-*, space-* and inset-* together, so one
      // definition covers the whole family.
      spacing: {
        hair: "2px", // icon to label, inline chip insets
        tight: "4px", // inside a control
        snug: "6px", // dense rows: chat activity, turn navigator
        base: "8px", // the app's default rhythm
        firm: "10px", // button sm horizontal padding
        soft: "12px", // card internals, list rows
        wide: "16px", // section padding, form groups
        roomy: "20px", // panel padding
        broad: "24px", // large containers
        deep: "32px", // oversized containers
        page: "40px", // page container vertical padding
        grand: "48px", // full-page shells: login, wizard, home
      },

      // Radii are named by what they wrap, so a card and a button cannot drift.
      borderRadius: {
        tile: "6px",
        card: "8px",
        sheet: "12px",
        pill: "999px",
      },

      // Content widths, named by what is being contained rather than how wide it
      // is. Measured from 183 call sites that previously spread over 33 distinct
      // values; nine settings pages at one nav level used four different page
      // widths, which is drift rather than design.
      //
      // Some values repeat under different names on purpose. `dialog` and
      // `controlWide` are both 448px today, but a modal and a text input are
      // different decisions and must be able to move apart without dragging
      // each other. Sharing the number would make the name meaningless.
      //
      // `sheet` is deliberately NOT used here — `rounded-sheet` already owns
      // that word at a different scale.
      maxWidth: {
        // A single control inside a settings row.
        control: "20rem", // 320px — numbers, short selects
        controlWide: "28rem", // 448px — text, IDs, model keys

        // Floating panels.
        dialog: "28rem", // 448px — confirm, gate, single-question modal
        dialogWide: "42rem", // 672px — multi-field modal
        dialogFull: "64rem", // 1024px — modal carrying a grid or preview surface
        drawer: "32rem", // 512px — right-anchored sheet
        drawerWide: "36rem", // 576px — wide drawer, grid column

        // Reading columns.
        measure: "42rem", // 672px — prose, chat turn, wide textarea
        thread: "48rem", // 768px — chat thread column and composer

        // Page containers. Three steps, decided 24.09.2026: the nine values
        // this replaced were not a scale, just nine separate decisions.
        pageNarrow: "48rem", // 768px
        page: "56rem", // 896px — the default page
        pageWide: "72rem", // 1152px — agents, projects, submissions

        // Truncation caps for dense data. Not layout: these bound how much of
        // one value is shown before it ellipsises.
        chip: "10rem", // 160px
        chipWide: "16rem", // 256px

        // Persistent side surfaces. Not drawers: a drawer opens and closes, a
        // rail is always there. The chat dock has exactly these two states.
        railNarrow: "14rem", // 224px — collapsed dock
        rail: "25rem", // 400px — expanded dock
      },

      // On dark surfaces the surface step does the lifting; the shadow only keeps
      // floating layers from looking pasted on.
      boxShadow: {
        panel: "0 1px 0 0 rgba(255, 255, 255, 0.03)",
        card: "0 1px 2px 0 rgba(0, 0, 0, 0.4), inset 0 1px 0 0 rgba(255, 255, 255, 0.03)",
        raised: "0 4px 12px -2px rgba(0, 0, 0, 0.55), inset 0 1px 0 0 rgba(255, 255, 255, 0.05)",
        overlay: "0 16px 40px -8px rgba(0, 0, 0, 0.7)",
        focus: "0 0 0 2px rgba(76, 141, 255, 0.55)",
      },

      transitionTimingFunction: {
        standard: "cubic-bezier(0.2, 0.7, 0.3, 1)",
      },
      transitionDuration: {
        fast: "110ms",
        normal: "170ms",
      },

      // A tooltip mounts on open, so it needs a keyframe rather than a
      // transition — there is no previous state to animate from. Kept at the
      // `fast` duration and the `standard` curve so it matches the rest of
      // the motion tokens, and the global prefers-reduced-motion rule in
      // index.css collapses it to an instant appearance without any
      // per-component handling.
      keyframes: {
        "tooltip-in": {
          from: { opacity: "0", transform: "translateY(2px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "tooltip-in": "tooltip-in 110ms cubic-bezier(0.2, 0.7, 0.3, 1)",
      },
    },
  },
  plugins: [],
};
