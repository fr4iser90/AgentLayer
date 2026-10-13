import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Mascot, pickCharacter } from "./Mascot";
import { MASCOTS, MASCOT_STATES, POSES, agentTurnState } from "./mascotArt";

/**
 * The mascot art is validated visually in the lab; what belongs in a unit test is
 * the wiring around it — that the agent's turn maps to the pose the user is told
 * about, that a user's character is stable rather than random per render, and
 * that mounting actually produces the SVG rather than silently swallowing a
 * driver error.
 */
describe("agentTurnState", () => {
  it("reads cancelled before anything else", () => {
    expect(agentTurnState({ running: true, hasReasoning: true, cancelled: true })).toBe("confused");
    expect(agentTurnState({ running: false, hasReasoning: false, cancelled: true })).toBe("confused");
  });

  it("separates reasoning from plain work while running", () => {
    expect(agentTurnState({ running: true, hasReasoning: true, cancelled: false })).toBe("thinking");
    expect(agentTurnState({ running: true, hasReasoning: false, cancelled: false })).toBe("working");
  });

  it("settles to happy once the turn is over", () => {
    expect(agentTurnState({ running: false, hasReasoning: true, cancelled: false })).toBe("happy");
  });
});

describe("pickCharacter", () => {
  it("is stable for the same identity", () => {
    const first = pickCharacter("admin@example.com");
    for (let i = 0; i < 25; i += 1) {
      expect(pickCharacter("admin@example.com")).toBe(first);
    }
  });

  it("spreads across all three characters rather than collapsing to one", () => {
    const seen = new Set<string>();
    for (let i = 0; i < 60; i += 1) seen.add(pickCharacter(`user${i}@example.com`));
    expect([...seen].sort()).toEqual(["nimbus", "pim", "volt"]);
  });

  it("falls back to the first character without a seed", () => {
    expect(pickCharacter(null)).toBe("pim");
    expect(pickCharacter("")).toBe("pim");
  });
});

describe("Mascot", () => {
  it("mounts a labelled svg rig", () => {
    render(<Mascot character="volt" state="idle" size={32} />);
    const img = screen.getByRole("img", { name: "Volt" });
    expect(img).toBeInTheDocument();
    expect(img.querySelector("svg")).not.toBeNull();
  });

  it("hides itself from assistive tech when asked to", () => {
    render(<Mascot character="pim" state="idle" ariaLabel={null} />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(document.querySelector('[aria-hidden="true"]')).not.toBeNull();
  });

  it("builds the rig into the host instead of leaving it empty", () => {
    const { container } = render(<Mascot character="nimbus" state="thinking" size={24} />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    // Every rig carries its own gradient + halo defs, keyed by a per-instance id.
    expect(svg!.querySelectorAll("defs radialGradient").length).toBeGreaterThanOrEqual(2);
    // Parts the driver needs must all exist on every character.
    expect(svg!.querySelectorAll("clipPath").length).toBe(2);
  });

  it("sizes itself from the size prop", () => {
    const { container } = render(<Mascot character="pim" state="idle" size={44} />);
    const host = container.firstElementChild as HTMLElement;
    expect(host.style.width).toBe("44px");
    expect(host.style.height).toBe("44px");
  });
});

describe("pose table", () => {
  it("exposes all 28 states", () => {
    expect(MASCOT_STATES).toHaveLength(28);
  });

  it("gives every state a mouth that exists", () => {
    for (const name of MASCOT_STATES) {
      expect(POSES[name].mouth).toBeTruthy();
    }
  });

  it("keeps idle and happy distinguishable by mouth", () => {
    // They used to share a smile and read as the same pose in the grid.
    expect(POSES.idle.mouth).not.toBe(POSES.happy.mouth);
  });

  it("keeps annoyed and overheated apart by extras", () => {
    // Both are gritted teeth; only one should vent steam.
    expect(POSES.annoyed.extras).not.toContain("steam");
    expect(POSES.overheated.extras).toContain("steam");
  });

  it("keeps confused and awkward apart by mouth", () => {
    expect(POSES.confused.mouth).not.toBe(POSES.awkward.mouth);
  });

  it("defines all three characters", () => {
    expect(Object.keys(MASCOTS).sort()).toEqual(["nimbus", "pim", "volt"]);
  });
});
