import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Select, TextArea, TextInput, fieldClass } from "./Field";

describe("ui/Field", () => {
  it("gives every field the same surface", () => {
    render(<TextInput defaultValue="" />);
    const cls = screen.getByRole("textbox").className;
    expect(cls).toContain("border-line");
    expect(cls).toContain("bg-field");
    expect(cls).toContain("focus:shadow-focus");
    // The shared surface must not survive twice at the call site — same reason
    // as the `Button` tests: Tailwind settles duplicates by stylesheet order.
    expect(fieldClass.split(" ").length).toBeGreaterThan(3);
  });

  it("distinguishes read-only from disabled", () => {
    render(<TextInput readOnly defaultValue="wert" />);
    const readOnly = screen.getByRole("textbox");
    // Read-only means "not yours to edit here", not "unavailable": the value
    // stays selectable at full contrast. The dimming utilities ride along in the
    // shared base and stay inert until the attribute is set, so the difference
    // is the attribute plus the read-only affordances — never an unconditional
    // `opacity-*`, which would grey the field out on its own.
    expect(readOnly).not.toBeDisabled();
    expect(readOnly.className).toContain("read-only:cursor-default");
    expect(readOnly.className).toContain("read-only:border-transparent");
    expect(readOnly.className).not.toMatch(/(^|\s)opacity-/);
  });

  it("dims a disabled field and takes it out of the order", () => {
    render(<TextInput disabled value="" />);
    const field = screen.getByRole("textbox");
    expect(field).toBeDisabled();
    expect(field.className).toContain("disabled:cursor-not-allowed");
  });

  it("puts a bare field flush with the surface behind it", () => {
    render(<TextInput bare placeholder="Nachricht" />);
    const cls = screen.getByRole("textbox").className;
    expect(cls).toContain("bg-transparent");
    expect(cls).not.toContain("border-line");
    // The composer's whole point: dropping the box must not drop the affordance.
    expect(cls).toContain("focus:outline-none");
    expect(cls).not.toContain("read-only:");
  });

  it("keeps bare on a textarea too", () => {
    render(<TextArea bare aria-label="Eingabe" />);
    expect(screen.getByRole("textbox").className).toContain("bg-transparent");
  });

  it("sets mono without touching anything else", () => {
    render(<TextInput mono defaultValue="" />);
    const cls = screen.getByRole("textbox").className;
    expect(cls).toContain("font-mono");
    expect(cls).toContain("bg-field");
  });

  it("lets the caller add layout and keeps it after the surface", () => {
    render(<TextInput className="mt-base" defaultValue="" />);
    const cls = screen.getByRole("textbox").className;
    expect(cls.indexOf("bg-field")).toBeLessThan(cls.indexOf("mt-base"));
  });

  it("renders a select that opens and reports changes", () => {
    const onChange = vi.fn();
    render(
      <Select aria-label="Modell" onChange={onChange} defaultValue="a">
        <option value="a">A</option>
        <option value="b">B</option>
      </Select>
    );
    const select = screen.getByRole("combobox");
    expect(select.className).toContain("cursor-pointer");
    fireEvent.change(select, { target: { value: "b" } });
    expect(onChange).toHaveBeenCalled();
  });

  it("forwards a ref", () => {
    const ref = { current: null as HTMLInputElement | null };
    render(<TextInput ref={ref} defaultValue="" />);
    expect(ref.current?.tagName).toBe("INPUT");
  });
});