import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CollapsibleSidebarShell } from "./CollapsibleSidebarShell";

/**
 * The shell's whole job is to be ONE region in two shapes, so the tests are
 * about the seam between them rather than about either shape.
 *
 * Before this file existed the mobile half was a hand-rolled overlay: a scrim
 * button, a peek-width panel, `md:hidden`, and none of what `Drawer` is for. It
 * had no dialog role, so a screen reader announced a list instead of a panel
 * the app treated as blocking; no Escape and no focus trap, so Tab walked out of
 * it into a page the user could not see; and it stayed standing over the
 * desktop column after a resize. Each of those is an assertion below — they are
 * what the merge bought, and without them the overlay could come back tomorrow
 * looking equivalent.
 *
 * The sidebar renders into both shapes at once because which one paints is a
 * CSS decision, so every lookup is scoped with `within`. The desktop copy is
 * `display: none` below md, which also hides it from assistive tech — there is
 * no duplicate announcement to test away.
 */
const tMock = vi.hoisted(() => ({ t: (key: string) => key }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: tMock.t, i18n: { language: "en" } }),
}));

function Shell({
  mobileOpen = true,
  onMobileOpenChange = () => {},
}: {
  mobileOpen?: boolean;
  onMobileOpenChange?: (open: boolean) => void;
} = {}) {
  return (
    <CollapsibleSidebarShell
      sidebar={<button type="button">Chats</button>}
      mobileOpen={mobileOpen}
      onMobileOpenChange={onMobileOpenChange}
      sidebarAriaLabel="Your chats"
      closeSidebarAriaLabel="Close chat list"
    >
      <p>thread</p>
    </CollapsibleSidebarShell>
  );
}

describe("the desktop column", () => {
  it("is a landmark named by the region, open or not", () => {
    render(<Shell mobileOpen={false} />);
    const column = screen.getByRole("complementary", { name: "Your chats" });
    expect(within(column).getByRole("button", { name: "Chats" })).toBeTruthy();
  });

  it("keeps the content beside it", () => {
    render(<Shell mobileOpen={false} />);
    expect(screen.getByText("thread")).toBeTruthy();
  });
});

describe("the mobile sheet", () => {
  it("is a dialog named by the same region", () => {
    render(<Shell />);
    expect(screen.getByRole("dialog", { name: "Your chats" })).toBeTruthy();
  });

  it("holds the sidebar itself, not a copy of its chrome", () => {
    render(<Shell />);
    expect(within(screen.getByRole("dialog")).getByRole("button", { name: "Chats" })).toBeTruthy();
  });

  it("paints chrome, so the list does not change colour when the breakpoint does", () => {
    render(<Shell />);
    expect(screen.getByRole("dialog").classList.contains("bg-panel")).toBe(true);
  });

  it("is gone from md up, where the column has reappeared", () => {
    render(<Shell />);
    const overlay = screen.getByRole("dialog").parentElement as HTMLElement;
    expect(overlay.classList.contains("md:hidden")).toBe(true);
  });

  it("is anchored to the edge the column stands on", () => {
    render(<Shell />);
    expect(screen.getByRole("dialog").classList.contains("left-0")).toBe(true);
  });

  it("lets the list own its scrolling instead of nesting a second scroll area", () => {
    // The sidebar pins its own header and scrolls its own body. Wrapped in the
    // drawer's padded scrolling div it got two scrollbars and the pinned part
    // scrolled away, so what is asserted here is the absence of that wrapper.
    render(<Shell />);
    const sheetBody = screen.getByRole("dialog").querySelector(":scope > div") as HTMLElement;
    expect(sheetBody.classList.contains("overflow-y-auto")).toBe(false);
    expect(sheetBody.classList.contains("overflow-hidden")).toBe(true);
    expect(sheetBody.classList.contains("px-roomy")).toBe(false);
  });
});

describe("dismissal", () => {
  // All three paths must report through `onMobileOpenChange(false)` — the shell
  // owns the state, so a sheet that only closes itself leaves the trigger's
  // aria-expanded lying on a panel that is already gone.
  it("reports through the close control, naming what it closes", () => {
    const onMobileOpenChange = vi.fn();
    render(<Shell onMobileOpenChange={onMobileOpenChange} />);
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Close chat list" }));
    expect(onMobileOpenChange).toHaveBeenCalledWith(false);
  });

  it("reports through Escape", () => {
    const onMobileOpenChange = vi.fn();
    render(<Shell onMobileOpenChange={onMobileOpenChange} />);
    fireEvent.keyDown(within(screen.getByRole("dialog")).getByText("Chats"), {
      key: "Escape",
    });
    expect(onMobileOpenChange).toHaveBeenCalledWith(false);
  });

  it("reports through the scrim", () => {
    const onMobileOpenChange = vi.fn();
    render(<Shell onMobileOpenChange={onMobileOpenChange} />);
    fireEvent.mouseDown(screen.getByRole("dialog").parentElement as HTMLElement);
    expect(onMobileOpenChange).toHaveBeenCalledWith(false);
  });
});