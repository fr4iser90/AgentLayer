import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Drawer } from "./Drawer";

/**
 * `Drawer` is the only sheet mechanism in the app, which means everything a
 * caller stopped hand-rolling has to be asserted HERE or it silently stops
 * existing. The four props this file is really about — `surface`, `mobileOnly`,
 * `flush`, `closeLabel` — were added when the collapsible sidebar's own overlay
 * moved in, and each one replaces code a caller used to write by hand.
 *
 * `react-i18next` is mocked so the default close label is the key itself: the
 * assertion is that the fallback reads `drawer.close`, not what English calls
 * it. A test that matched on "Close panel" would pass while the component read
 * a different key entirely.
 */
const tMock = vi.hoisted(() => ({ t: (key: string) => key }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: tMock.t, i18n: { language: "en" } }),
}));

function Sheet({
  open = true,
  onClose = () => {},
  ...rest
}: Partial<React.ComponentProps<typeof Drawer>> = {}) {
  return (
    <Drawer open={open} onClose={onClose} title="Chat list" {...rest}>
      <button type="button">first</button>
      <button type="button">last</button>
    </Drawer>
  );
}

const scrim = () => screen.getByRole("dialog").parentElement as HTMLElement;
const body = () => screen.getByText("first").parentElement as HTMLElement;

describe("Drawer is a dialog", () => {
  it("renders nothing while closed", () => {
    render(<Sheet open={false} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("declares itself and takes its name from the title", () => {
    render(<Sheet />);
    const dialog = screen.getByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog).toHaveAccessibleName("Chat list");
  });

  it("takes focus into the panel, which is what a hand-rolled overlay never did", () => {
    render(<Sheet />);
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(<Sheet onClose={onClose} />);
    fireEvent.keyDown(screen.getByText("first"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("scrim", () => {
  it("closes when the scrim itself is pressed", () => {
    const onClose = vi.fn();
    render(<Sheet onClose={onClose} />);
    fireEvent.mouseDown(scrim());
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("stays open when a press inside the panel bubbles up to it", () => {
    const onClose = vi.fn();
    render(<Sheet onClose={onClose} />);
    fireEvent.mouseDown(screen.getByText("first"));
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("mobileOnly", () => {
  // The property that keeps a replacement drawer from becoming a second
  // navigation. A sheet that survives its own desktop region is not just twice
  // the chrome: the hidden copy keeps holding the focus trap, so Tab walks
  // around controls nobody can see.
  it("hides the sheet from md up", () => {
    render(<Sheet mobileOnly />);
    expect(scrim().classList.contains("md:hidden")).toBe(true);
  });

  it("stays on screen at every width by default", () => {
    render(<Sheet />);
    expect(scrim().classList.contains("md:hidden")).toBe(false);
  });
});

describe("surface", () => {
  // Two `bg-*` utilities on one element are decided by stylesheet order, not by
  // the order they are written, so a caller could not override the fill even if
  // the primitive forwarded `className`. These assert the chosen class AND the
  // absence of the other, which is the only way to see a hard-coded `bg-card`
  // that never left the base class list.
  it("paints a content container by default", () => {
    render(<Sheet />);
    const panel = screen.getByRole("dialog");
    expect(panel.classList.contains("bg-card")).toBe(true);
    expect(panel.classList.contains("bg-panel")).toBe(false);
  });

  it("paints chrome when it stands in for a desktop region", () => {
    render(<Sheet surface="panel" />);
    const panel = screen.getByRole("dialog");
    expect(panel.classList.contains("bg-panel")).toBe(true);
    expect(panel.classList.contains("bg-card")).toBe(false);
  });
});

describe("flush", () => {
  it("pads and scrolls the body by default", () => {
    render(<Sheet />);
    const cls = body().classList;
    expect(cls.contains("px-roomy")).toBe(true);
    expect(cls.contains("overflow-y-auto")).toBe(true);
  });

  it("hands padding and scrolling to the content when asked", () => {
    render(<Sheet flush />);
    const cls = body().classList;
    expect(cls.contains("px-roomy")).toBe(false);
    expect(cls.contains("overflow-y-auto")).toBe(false);
    expect(cls.contains("overflow-hidden")).toBe(true);
    expect(cls.contains("flex-col")).toBe(true);
  });
});

describe("close control", () => {
  it("falls back to the shared label", () => {
    render(<Sheet />);
    expect(within(screen.getByRole("dialog")).getByRole("button", { name: "drawer.close" })).toBeTruthy();
  });

  it("takes a caller's label when the page has more than one panel", () => {
    render(<Sheet closeLabel="Close chat list" />);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Close chat list" })).toBeTruthy();
    expect(within(dialog).queryByRole("button", { name: "drawer.close" })).toBeNull();
  });

  it("closing through it reaches onClose", () => {
    const onClose = vi.fn();
    render(<Sheet onClose={onClose} closeLabel="Close chat list" />);
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Close chat list" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("swipe", () => {
  // A leftward swipe means "go back" over a left rail and "dismiss the
  // keyboard" over a bottom sheet, so only the right-anchored variant may
  // treat it as dismissal. The sidebar merge made this observable: the sheet it
  // replaced swiped shut from the left edge of the screen.
  const swipeLeft = (el: HTMLElement) => {
    fireEvent.touchStart(el, { touches: [{ clientX: 240, clientY: 120 }] });
    fireEvent.touchEnd(el, { changedTouches: [{ clientX: 120, clientY: 128 }] });
  };

  it("closes a right-anchored sheet", () => {
    const onClose = vi.fn();
    render(<Sheet onClose={onClose} />);
    swipeLeft(screen.getByRole("dialog"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("leaves a left-anchored sheet alone", () => {
    const onClose = vi.fn();
    render(<Sheet onClose={onClose} side="left" />);
    swipeLeft(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("ignores a drag shorter than the threshold", () => {
    const onClose = vi.fn();
    render(<Sheet onClose={onClose} />);
    fireEvent.touchStart(screen.getByRole("dialog"), { touches: [{ clientX: 240, clientY: 120 }] });
    fireEvent.touchEnd(screen.getByRole("dialog"), { changedTouches: [{ clientX: 200, clientY: 122 }] });
    expect(onClose).not.toHaveBeenCalled();
  });
});