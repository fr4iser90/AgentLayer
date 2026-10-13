import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Radio } from "./Radio";

describe("ui/Radio", () => {
  it("is still a radio in a named group", () => {
    render(<Radio value="fast" name="speed" defaultChecked={false} aria-label="Schnell" />);
    const box = screen.getByRole("radio");
    expect(box.getAttribute("name")).toBe("speed");
    expect(box.getAttribute("value")).toBe("fast");
    // The group is the point of the control: a lost name silently turns a
    // single choice into three independently checked boxes.
    expect(box.className).toContain("appearance-none");
    expect(box.className).toContain("rounded-pill");
  });

  it("fills the box and puts the dot in the ink that passes on it", () => {
    render(<Radio defaultChecked aria-label="Schnell" />);
    const cls = screen.getByRole("radio").className;
    expect(cls).toContain("checked:bg-accent");
    expect(cls).toContain("after:bg-ink-on-fill");
    expect(cls).not.toMatch(/after:bg-white/);
    expect(cls).toContain("after:content-['']");
  });

  it("shows the dot only while selected", () => {
    render(<Radio defaultChecked={false} aria-label="Schnell" />);
    const cls = screen.getByRole("radio").className;
    expect(cls).toContain("after:opacity-0");
    expect(cls).toContain("checked:after:opacity-100");
  });

  it("hands the caller the selected value", () => {
    const onChange = vi.fn();
    render(<Radio value="slow" checked={false} onChange={onChange} aria-label="Langsam" />);
    fireEvent.click(screen.getByRole("radio"));
    expect(onChange.mock.calls[0][0].target.value).toBe("slow");
  });

  it("dims and drops out of the order when disabled", () => {
    render(<Radio disabled checked={false} aria-label="Langsam" />);
    const box = screen.getByRole("radio");
    expect(box).toBeDisabled();
    expect(box.className).toContain("disabled:cursor-not-allowed");
    expect(box.className).not.toMatch(/(^|\s)opacity-/);
  });

  it("keeps its own box when the caller adds layout", () => {
    render(<Radio defaultChecked={false} className="mt-hair" aria-label="Langsam" />);
    const cls = screen.getByRole("radio").className;
    expect(cls).toContain("mt-hair");
    expect(cls).toContain("h-4 w-4");
  });

  it("forwards the ref to the input", () => {
    const ref = createRef<HTMLInputElement>();
    render(<Radio ref={ref} defaultChecked aria-label="Schnell" />);
    expect(ref.current?.getAttribute("type")).toBe("radio");
  });
});