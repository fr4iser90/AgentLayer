import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { Listbox } from "./Listbox";

const OPTIONS = [
  { value: "a", label: "Erstes Modell", hint: "anbieter-a" },
  { value: "b", label: "Zweites Modell" },
  { value: "c", label: "Grau", disabled: true },
];

describe("ui/Listbox", () => {
  it("puts the option role and the selection state on the same element", () => {
    render(<Listbox options={OPTIONS} value="b" onSelect={() => {}} ariaLabel="Modell" />);
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(3);
    // A <button role="option"> inside a listbox announces twice; the option is
    // the row, not a button inside it.
    expect(within(options[1]).queryByRole("button")).not.toBeInTheDocument();
    expect(options[1]).toHaveAttribute("aria-selected", "true");
    expect(options[0]).toHaveAttribute("aria-selected", "false");
  });

  it("starts focus on the selected option", () => {
    render(<Listbox options={OPTIONS} value="b" onSelect={() => {}} ariaLabel="Modell" />);
    expect(document.activeElement).toHaveTextContent("Zweites Modell");
  });

  it("skips the disabled option when arrowing", () => {
    render(<Listbox options={OPTIONS} value="b" onSelect={() => {}} ariaLabel="Modell" />);
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "ArrowDown" });
    expect(document.activeElement).toHaveTextContent("Zweites Modell");
    expect(document.activeElement).not.toHaveTextContent("Grau");
  });

  it("selects on click and on Enter, and closes both times", () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    render(<Listbox options={OPTIONS} value="a" onSelect={onSelect} onClose={onClose} ariaLabel="Modell" />);
    fireEvent.click(screen.getByText("Erstes Modell"));
    expect(onSelect).toHaveBeenCalledWith("a");
    // Focus sits on the selected option, so Enter picks "a" — Enter follows
    // focus, it does not repeat the last click.
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Enter" });
    expect(onSelect).toHaveBeenLastCalledWith("a");
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("shows the empty content instead of an empty scroller", () => {
    render(<Listbox options={[]} value="" onSelect={() => {}} ariaLabel="Threads" empty="Keine Threads" />);
    expect(screen.getByText("Keine Threads")).toBeInTheDocument();
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
  });
});