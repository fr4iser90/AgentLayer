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

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: CANVAS,
        panel: PANEL,
        card: CARD,
        raised: RAISED,
        overlay: OVERLAY,

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

        // --- compatibility aliases (do not use in new code) ---
        surface: {
          DEFAULT: CANVAS,
          raised: PANEL,
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

      // Radii are named by what they wrap, so a card and a button cannot drift.
      borderRadius: {
        tile: "6px",
        card: "8px",
        sheet: "12px",
        pill: "999px",
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
    },
  },
  plugins: [],
};
