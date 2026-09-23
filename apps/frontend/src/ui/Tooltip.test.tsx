import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  EDGE,
  GAP,
  HIDE_DELAY,
  HOVER_DELAY,
  TOUCH_SUPPRESS_MS,
  Tooltip,
  place,
} from "./Tooltip";

/**
 * jsdom performs no layout, so getBoundingClientRect() returns zeros everywhere
 * and the placement decision cannot be observed through a rendered component.
 * The arithmetic is therefore exported and tested directly — that is the part
 * with real branches in it. The live behaviour (does the bubble really escape an
 * overflow container, does the pointer really survive the gap) is verified in a
 * browser probe, not here.
 */
describe("place", () => {
  const trigger = { x: 100, y: 100, width: 40, height: 20 };
  const tip = { width: 80, height: 30 };
  const vp = { width: 1000, height: 800 };

  it("centres above the trigger when there is room", () => {
    const r = place(trigger, tip, vp, "top");
    expect(r.placement).toBe("top");
    expect(r.top).toBe(100 - 30 - GAP);
    expect(r.left).toBe(100 + 20 - 40);
  });

  it("flips below when the trigger sits too close to the top edge", () => {
    const r = place({ ...trigger, y: 20 }, tip, vp, "top");
    expect(r.placement).toBe("bottom");
    expect(r.top).toBe(20 + 20 + GAP);
  });

  it("flips to the right when there is no room on the left", () => {
    const r = place({ ...trigger, x: 20 }, tip, vp, "left");
    expect(r.placement).toBe("right");
    expect(r.left).toBe(20 + 40 + GAP);
  });

  it("flips to the left when the right edge is too close", () => {
    const r = place({ ...trigger, x: 960 }, tip, vp, "right");
    expect(r.placement).toBe("left");
    expect(r.left).toBe(960 - 80 - GAP);
  });

  it("keeps the edge margin instead of hanging off the viewport", () => {
    // Bubble wider than the space available on either side of the trigger.
    const r = place({ x: 10, y: 100, width: 20, height: 20 }, { width: 90, height: 30 }, { width: 100, height: 800 }, "top");
    expect(r.left).toBe(EDGE);
  });

  it("reports a bottom placement that genuinely fits", () => {
    // fits.bottom is exactly `top + height <= viewport - edge`, so a chosen
    // bottom can never also need a vertical clamp. This asserts the chosen
    // coordinates stay inside the margin rather than a state that cannot occur.
    const r = place({ x: 100, y: 700, width: 40, height: 20 }, tip, { width: 1000, height: 800 }, "bottom");
    expect(r.placement).toBe("bottom");
    expect(r.top).toBe(700 + 20 + GAP);
    expect(r.top + tip.height).toBeLessThanOrEqual(800 - EDGE);
  });

  it("keeps the preferred side and clamps when neither side fits", () => {
    // 60px tall viewport cannot hold a 50px bubble above or below a trigger at y=20.
    const r = place({ x: 100, y: 20, width: 40, height: 20 }, { width: 80, height: 50 }, { width: 1000, height: 60 }, "top");
    expect(r.placement).toBe("top");
    expect(r.top).toBeGreaterThanOrEqual(EDGE);
  });

  it("centres vertically on horizontal placements", () => {
    const r = place(trigger, tip, vp, "left");
    expect(r.top).toBe(100 + 10 - 15);
  });
});

describe("Tooltip", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("renders the child untouched when there is no label", () => {
    render(
      <Tooltip label="">
        <button type="button">los</button>
      </Tooltip>,
    );
    const btn = screen.getByRole("button", { name: "los" });
    expect(btn).not.toHaveAttribute("aria-describedby");
    fireEvent.focus(btn);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("shows on focus and links the trigger with aria-describedby", () => {
    render(
      <Tooltip label="Kontext offen">
        <button type="button">ctx</button>
      </Tooltip>,
    );
    const btn = screen.getByRole("button", { name: "ctx" });
    // jsdom evaluates :focus-visible against real focus state, so the element
    // has to actually be focused — firing focus alone does not open it, which
    // is the gate working rather than the test being weak.
    btn.focus();
    fireEvent.focus(btn);
    const tip = screen.getByRole("tooltip");
    expect(tip).toHaveTextContent("Kontext offen");
    expect(btn.getAttribute("aria-describedby")).toBe(tip.id);
  });

  it("does not open on a focus event from an unfocused element", () => {
    render(
      <Tooltip label="nicht">
        <button type="button">keinfokus</button>
      </Tooltip>,
    );
    fireEvent.focus(screen.getByRole("button", { name: "keinfokus" }));
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("drops aria-describedby once closed so no dangling reference is left", () => {
    render(
      <Tooltip label="weg">
        <button type="button">b</button>
      </Tooltip>,
    );
    const btn = screen.getByRole("button", { name: "b" });
    btn.focus();
    fireEvent.focus(btn);
    expect(btn).toHaveAttribute("aria-describedby");
    fireEvent.blur(btn);
    expect(screen.queryByRole("tooltip")).toBeNull();
    expect(btn).not.toHaveAttribute("aria-describedby");
  });

  it("dismisses on Escape and returns focus to the trigger", () => {
    render(
      <Tooltip label="flucht">
        <button type="button">zuruck</button>
      </Tooltip>,
    );
    const btn = screen.getByRole("button", { name: "zuruck" });
    btn.focus();
    fireEvent.focus(btn);
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
    expect(document.activeElement).toBe(btn);
  });

  it("waits out the hover delay before opening on pointer hover", () => {
    render(
      <Tooltip label="spaeter">
        <button type="button">h</button>
      </Tooltip>,
    );
    const btn = screen.getByRole("button", { name: "h" });
    fireEvent.pointerEnter(btn, { pointerType: "mouse" });
    expect(screen.queryByRole("tooltip")).toBeNull();
    act(() => vi.advanceTimersByTime(HOVER_DELAY));
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
  });

  it("suppresses hover for a window after a touch", () => {
    // jsdom has no PointerEvent constructor, so `pointerType` arrives undefined
    // and cannot be asserted here — the pointerType branch is verified in the
    // browser probe. The touchstart timestamp is the touch signal jsdom can
    // actually exercise, and it is the one that matters anyway: touch devices
    // follow a tap with synthetic mouse/pointer events.
    render(
      <Tooltip label="beruhrung">
        <button type="button">t</button>
      </Tooltip>,
    );
    const btn = screen.getByRole("button", { name: "t" });
    fireEvent.touchStart(btn);
    fireEvent.pointerEnter(btn);
    act(() => vi.advanceTimersByTime(HOVER_DELAY * 3));
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("allows hover again once the touch window has passed", () => {
    render(
      <Tooltip label="danach">
        <button type="button">t2</button>
      </Tooltip>,
    );
    const btn = screen.getByRole("button", { name: "t2" });
    fireEvent.touchStart(btn);
    act(() => vi.advanceTimersByTime(TOUCH_SUPPRESS_MS + 10));
    fireEvent.pointerEnter(btn);
    act(() => vi.advanceTimersByTime(HOVER_DELAY));
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
  });

  it("stays open while the pointer crosses onto the bubble", () => {
    render(
      <Tooltip label="bleib">
        <button type="button">uiber</button>
      </Tooltip>,
    );
    const btn = screen.getByRole("button", { name: "uiber" });
    fireEvent.pointerEnter(btn, { pointerType: "mouse" });
    act(() => vi.advanceTimersByTime(HOVER_DELAY));
    const tip = screen.getByRole("tooltip");
    fireEvent.pointerLeave(btn, { pointerType: "mouse" });
    // Inside the grace window the bubble must still be there to be hovered.
    act(() => vi.advanceTimersByTime(HIDE_DELAY - 20));
    expect(screen.getByRole("tooltip")).toBe(tip);
    fireEvent.pointerEnter(tip, { pointerType: "mouse" });
    act(() => vi.advanceTimersByTime(HIDE_DELAY * 3));
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
  });

  it("closes after the grace window if the pointer never reaches the bubble", () => {
    render(
      <Tooltip label="fort">
        <button type="button">lass</button>
      </Tooltip>,
    );
    const btn = screen.getByRole("button", { name: "lass" });
    fireEvent.pointerEnter(btn, { pointerType: "mouse" });
    act(() => vi.advanceTimersByTime(HOVER_DELAY));
    fireEvent.pointerLeave(btn, { pointerType: "mouse" });
    act(() => vi.advanceTimersByTime(HIDE_DELAY + 10));
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("preserves the child's own pointer handler", () => {
    const seen = vi.fn();
    render(
      <Tooltip label="mit">
        <button type="button" onPointerEnter={seen}>
          beide
        </button>
      </Tooltip>,
    );
    fireEvent.pointerEnter(screen.getByRole("button", { name: "beide" }), { pointerType: "mouse" });
    expect(seen).toHaveBeenCalledTimes(1);
  });
});
