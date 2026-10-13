import { act, fireEvent, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { useClickOutside } from "./useClickOutside";

/**
 * Four popovers kept their own copy of this — three on `mousedown`, one on
 * `pointerdown` — and two of them had no Escape handler at all. The copies are
 * gone now, so what is pinned here is the behaviour the copies did not all
 * share, plus the two ways a naive implementation of the hook would break them:
 *
 * - `mousedown` fires twice for one tap on a touch device (once native, once
 *   synthesised), which closed a menu and reopened it. Listening to `pointerdown`
 *   only is the fix, so a tap that produces both events must dismiss once.
 * - The callback lives in a ref so an inline arrow at the call site does not
 *   re-subscribe a document listener every render. A stale ref would keep
 *   calling the first render's closure, which captures the first render's state.
 */

function Popover({ onOutside, enabled }: { onOutside: () => void; enabled?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, onOutside, enabled);
  return (
    <div>
      <div ref={ref} data-testid="pop">
        <button type="button" data-testid="inside">
          inside
        </button>
      </div>
      <button type="button" data-testid="outside">
        outside
      </button>
    </div>
  );
}

const outside = () => screen.getByTestId("outside");

describe("useClickOutside", () => {
  it("dismisses on a pointer down outside the element", () => {
    const onOutside = vi.fn();
    render(<Popover onOutside={onOutside} enabled />);
    act(() => fireEvent.pointerDown(outside()));
    expect(onOutside).toHaveBeenCalledTimes(1);
  });

  it("leaves a pointer down inside alone", () => {
    const onOutside = vi.fn();
    render(<Popover onOutside={onOutside} enabled />);
    act(() => fireEvent.pointerDown(screen.getByTestId("inside")));
    expect(onOutside).not.toHaveBeenCalled();
  });

  it("dismisses on Escape", () => {
    const onOutside = vi.fn();
    render(<Popover onOutside={onOutside} enabled />);
    act(() => fireEvent.keyDown(document, { key: "Escape" }));
    expect(onOutside).toHaveBeenCalledTimes(1);
  });

  it("counts one tap as one dismissal, not two", () => {
    // A touch tap arrives as pointerdown and then a synthesised mousedown. The
    // copies that listened to mousedown closed the menu and reopened it.
    const onOutside = vi.fn();
    render(<Popover onOutside={onOutside} enabled />);
    act(() => {
      fireEvent.pointerDown(outside());
      fireEvent.mouseDown(outside());
    });
    expect(onOutside).toHaveBeenCalledTimes(1);
  });

  it("does nothing while disabled", () => {
    const onOutside = vi.fn();
    render(<Popover onOutside={onOutside} enabled={false} />);
    act(() => {
      fireEvent.pointerDown(outside());
      fireEvent.keyDown(document, { key: "Escape" });
    });
    expect(onOutside).not.toHaveBeenCalled();
  });

  it("calls the latest callback after a re-render", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = render(<Popover onOutside={first} enabled />);
    rerender(<Popover onOutside={second} enabled />);
    act(() => fireEvent.pointerDown(outside()));
    expect(second).toHaveBeenCalledTimes(1);
    expect(first).not.toHaveBeenCalled();
  });

  it("removes its listeners on unmount", () => {
    const onOutside = vi.fn();
    const { unmount } = render(<Popover onOutside={onOutside} enabled />);
    // The anchor has to outlive the component: firing on a node the render
    // already detached would prove nothing, because it never reaches document.
    const anchor = document.createElement("button");
    document.body.appendChild(anchor);
    unmount();
    act(() => {
      fireEvent.pointerDown(anchor);
      fireEvent.keyDown(document, { key: "Escape" });
    });
    anchor.remove();
    expect(onOutside).not.toHaveBeenCalled();
  });
});