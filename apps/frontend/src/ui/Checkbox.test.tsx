import { createRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Checkbox } from "./Checkbox";

describe("ui/Checkbox", () => {
  it("takes the box away from the user agent", () => {
    render(<Checkbox defaultChecked={false} aria-label="Etwas erlauben" />);
    const box = screen.getByRole("checkbox");
    // Without this one class every other class below is painted over by the
    // browser's own widget — the state the 60 unstyled checkboxes were in.
    expect(box.className).toContain("appearance-none");
    expect(box.className).toContain("h-4 w-4");
    expect(box.className).toContain("border-line");
    expect(box.className).toContain("bg-field");
  });

  it("draws the tick in the ink that passes on the fill", () => {
    render(<Checkbox defaultChecked aria-label="Etwas erlauben" />);
    const cls = screen.getByRole("checkbox").className;
    expect(cls).toContain("checked:bg-accent");
    expect(cls).toContain("after:border-ink-on-fill");
    // White on a saturated fill is the pair that fails contrast (2.52-3.35:1).
    expect(cls).not.toMatch(/after:border-white|after:bg-white/);
    // A pseudo-element without `content` renders no box: the tick would be
    // missing while the class list still read complete.
    expect(cls).toContain("after:content-['']");
  });

  it("shows the tick only while checked", () => {
    render(<Checkbox defaultChecked={false} aria-label="Etwas erlauben" />);
    const cls = screen.getByRole("checkbox").className;
    expect(cls).toContain("after:opacity-0");
    // Both halves are needed: hidden by default and revealed by the state.
    expect(cls).toContain("checked:after:opacity-100");
  });

  it("hands the caller the checked flag", () => {
    const onChange = vi.fn();
    // Uncontrolled on purpose: React puts a controlled input back to its prop
    // before the handler reads it, so `checked={false}` here would test the
    // reconciliation order rather than what the primitive passes through.
    render(<Checkbox defaultChecked={false} onChange={onChange} aria-label="Etwas erlauben" />);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0].target.checked).toBe(true);
  });

  it("toggles for the controlled caller the app writes", () => {
    function Row() {
      const [on, setOn] = useState(false);
      return (
        <Checkbox
          checked={on}
          onChange={(e) => setOn(e.target.checked)}
          aria-label="Etwas erlauben"
        />
      );
    }
    render(<Row />);
    const box = screen.getByRole("checkbox") as HTMLInputElement;
    expect(box.checked).toBe(false);
    fireEvent.click(box);
    // The whole reason the migration is mechanical: the primitive must not eat
    // the checked/onChange pair the 88 controlled call sites already pass.
    expect(box.checked).toBe(true);
  });

  it("grows the target without leaving the other size in the class list", () => {
    render(<Checkbox size="lg" defaultChecked={false} aria-label="Etwas erlauben" />);
    const cls = screen.getByRole("checkbox").className;
    expect(cls).toContain("h-5 w-5");
    // Two sizes in one class list are settled by stylesheet order, not intent.
    expect(cls).not.toContain("h-4 ");
    expect(cls).toContain("after:h-2.5");
  });

  it("dims a disabled box and keeps the dimming conditional", () => {
    render(<Checkbox disabled checked={false} aria-label="Etwas erlauben" />);
    const box = screen.getByRole("checkbox");
    expect(box).toBeDisabled();
    expect(box.className).toContain("disabled:cursor-not-allowed");
    expect(box.className).not.toMatch(/(^|\s)opacity-/);
  });

  it("appends the caller's layout after its own box", () => {
    render(<Checkbox defaultChecked={false} className="mt-tight" aria-label="Etwas erlauben" />);
    const cls = screen.getByRole("checkbox").className;
    expect(cls).toContain("mt-tight");
    expect(cls.indexOf("mt-tight")).toBeGreaterThan(cls.indexOf("appearance-none"));
  });

  it("forwards the ref to the input, not to a wrapper", () => {
    const ref = createRef<HTMLInputElement>();
    render(<Checkbox ref={ref} defaultChecked aria-label="Etwas erlauben" />);
    expect(ref.current?.getAttribute("type")).toBe("checkbox");
  });
});