import React from "react";
import { createRoot } from "react-dom/client";
import "../../src/index.css";
import { Tooltip } from "../../src/ui/Tooltip";

/**
 * Fixture for the browser probe. Every container here exists to break a tooltip
 * that is positioned with `absolute` inside its trigger's wrapper, which is what
 * the app's existing popovers do. If the portal works, none of them clip.
 */
function App() {
  return (
    <div style={{ padding: 24, display: "grid", gap: 40 }}>
      {/* overflow:hidden with the trigger at the container's top edge and enough
          clear space above the container that a "top" tooltip fits the viewport
          while still extending past the container's own top edge. That is the
          only geometry in which an absolutely positioned bubble would actually
          be clipped and a portalled one would not. */}
      <section
        id="clipbox"
        style={{
          overflow: "hidden",
          height: 90,
          marginTop: 170,
          border: "1px solid #2E343E",
          background: "#1E222A",
          padding: 8,
        }}
      >
        <Tooltip label="Entkommt overflow:hidden">
          <button id="t-clip" type="button" style={{ padding: "6px 12px" }}>
            in Clip-Box
          </button>
        </Tooltip>
      </section>

      {/* A table-like horizontal scroller, the common chat/dashboard shape. */}
      <section
        id="scrollbox"
        style={{
          overflowX: "auto",
          border: "1px solid #2E343E",
          background: "#15181D",
          padding: 8,
        }}
      >
        <div style={{ width: 1600, display: "flex", gap: 12, alignItems: "center" }}>
          <span style={{ color: "#B4BAC4" }}>breite Zeile</span>
          <Tooltip label="Entkommt overflow-x:auto">
            <button id="t-scroll" type="button" style={{ padding: "6px 12px" }}>
              im Scroller
            </button>
          </Tooltip>
        </div>
      </section>

      {/* Long label: must wrap inside the max width, not run off screen. */}
      <Tooltip label="Ein deutlich längerer Tooltip-Text, der zeigen soll, dass die maximale Breite hält und der Text sauber umbricht statt über den Rand zu laufen.">
        <button id="t-long" type="button" style={{ padding: "6px 12px" }}>
          langer Text
        </button>
      </Tooltip>

      {/* A link inside the bubble: only usable if the bubble survives the gap. */}
      <Tooltip
        label={
          <span>
            <a id="tip-link" href="#x" style={{ color: "#4C8DFF" }}>
              Link im Tooltip
            </a>
          </span>
        }
      >
        <button id="t-link" type="button" style={{ padding: "6px 12px" }}>
          mit Link
        </button>
      </Tooltip>

      {/* Flush against the viewport top: no room above, must flip. Fixed so it is
          genuinely at the edge rather than merely near it. */}
      <div style={{ position: "fixed", top: 4, left: 8 }}>
        <Tooltip label="Kante oben — muss nach unten klappen">
          <button id="t-top" type="button" style={{ padding: "6px 12px" }}>
            oben
          </button>
        </Tooltip>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
