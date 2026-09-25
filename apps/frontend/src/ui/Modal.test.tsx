import { fireEvent, render, screen, within } from "@testing-library/react";
import { useRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { Modal } from "./Modal";

/**
 * The app shipped 16 overlays, 6 of them visually a dialog, and a focus trap
 * nowhere. These tests exist to make that state fail: a dialog that lets Tab
 * walk out into a page the user can no longer see is the defect, so the wrap
 * assertions are the point, not decoration.
 *
 * Focus order inside the panel is [close, ...body]. The header's close button
 * is a real focusable and comes first — an earlier version of this file assumed
 * the body's first control did and failed for the right reason.
 */
function Harness({
  onClose = () => {},
  dismissOnScrim,
}: {
  onClose?: () => void;
  dismissOnScrim?: boolean;
}) {
  const trigger = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button ref={trigger} type="button">
        trigger
      </button>
      <Modal open onClose={onClose} title="Export settings" dismissOnScrim={dismissOnScrim}>
        <button type="button">first</button>
        <button type="button">last</button>
      </Modal>
    </>
  );
}

function panel() {
  const dialog = screen.getByRole("dialog");
  return { dialog, buttons: within(dialog).getAllByRole("button") };
}

describe("Modal is a dialog", () => {
  it("declares itself and names itself from the title", () => {
    render(<Harness />);
    const dialog = screen.getByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    const labelledBy = dialog.getAttribute("aria-labelledby");
    expect(labelledBy).toBeTruthy();
    expect(document.getElementById(labelledBy ?? "")?.textContent).toBe("Export settings");
  });

  it("moves focus into the dialog on open", () => {
    render(<Harness />);
    const { dialog } = panel();
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    fireEvent.keyDown(screen.getByText("first"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("Modal holds the tab order", () => {
  it("wraps forward from the last control to the first", () => {
    render(<Harness />);
    const { buttons } = panel();
    expect(buttons).toHaveLength(3);
    const [closeBtn, , last] = buttons;
    last.focus();
    fireEvent.keyDown(last, { key: "Tab" });
    expect(document.activeElement).toBe(closeBtn);
  });

  it("wraps backward from the first control to the last", () => {
    render(<Harness />);
    const { buttons } = panel();
    const [closeBtn, , last] = buttons;
    closeBtn.focus();
    fireEvent.keyDown(closeBtn, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);
  });

  it("leaves a mid-list Tab to the browser", () => {
    // Guards against a trap that wraps on every keystroke. Only the two edges
    // are its business: Shift+Tab from a middle control must not jump to the
    // end. (A FORWARD mid-list Tab cannot be asserted at all — jsdom has no
    // default tab order, so a trap that does nothing is indistinguishable from
    // one that moved focus onward, and pretending otherwise would be a test
    // that cannot fail.)
    render(<Harness />);
    const { buttons } = panel();
    expect(buttons).toHaveLength(3);
    const [, middle] = buttons;
    middle.focus();
    fireEvent.keyDown(middle, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(middle);
  });

  it("ignores a Tab whose focus is outside the dialog", () => {
    // A dialog nested in a drawer must not steal its child's tab order.
    render(<Harness />);
    const outside = screen.getByText("trigger");
    outside.focus();
    fireEvent.keyDown(outside, { key: "Tab" });
    expect(document.activeElement).toBe(outside);
  });

  it("skips a control the dialog hid", () => {
    render(
      <Modal open onClose={() => {}} title="Hidden">
        <div hidden>
          <button type="button">stowed</button>
        </div>
        <button type="button">shown</button>
      </Modal>
    );
    const { dialog } = panel();
    const [closeBtn] = within(dialog).getAllByRole("button");
    closeBtn.focus();
    // Shift+Tab from the first control wraps to the LAST one, which is the
    // assertion that can actually fail: if the hidden control were still a
    // candidate it would be last, and `shown` would not be focused. A forward
    // Tab cannot show this — jsdom implements no default tab order, so a trap
    // that does nothing looks identical to one that moved focus onward.
    fireEvent.keyDown(closeBtn, { key: "Tab", shiftKey: true });
    // `offsetParent` is always null in jsdom, so a visibility filter built on
    // it would collect nothing here and the trap would pass while doing
    // nothing. `[hidden]` is what the trap actually reads.
    expect(document.activeElement).toBe(screen.getByText("shown"));
  });

  it("returns focus to the trigger when it unmounts", () => {
    const trigger = document.createElement("button");
    document.body.appendChild(trigger);
    trigger.focus();
    const view = render(
      <Modal open onClose={() => {}} title="Away">
        <button type="button">inside</button>
      </Modal>
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog.contains(document.activeElement)).toBe(true);
    view.unmount();
    expect(document.activeElement).toBe(trigger);
    document.body.removeChild(trigger);
  });
});

describe("Modal scrim", () => {
  it("closes when the scrim itself is pressed", () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const scrim = screen.getByRole("dialog").parentElement as HTMLElement;
    fireEvent.mouseDown(scrim);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("stays open on a scrim press when dismissal is off", () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} dismissOnScrim={false} />);
    const scrim = screen.getByRole("dialog").parentElement as HTMLElement;
    fireEvent.mouseDown(scrim);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("does not close when a press inside the panel reaches the scrim", () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    fireEvent.mouseDown(screen.getByText("first"));
    expect(onClose).not.toHaveBeenCalled();
  });
});