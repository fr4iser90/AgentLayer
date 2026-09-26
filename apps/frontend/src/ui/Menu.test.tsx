import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Menu } from "./Menu";

const ITEMS = [
  { id: "one", label: "Erste Aktion" },
  { id: "two", label: "Zweite Aktion" },
  { id: "off", label: "Deaktiviert", disabled: true },
];

describe("ui/Menu", () => {
  it("renders one menuitem per entry and focuses the first enabled one", () => {
    render(<Menu items={ITEMS} onClose={() => {}} />);
    expect(screen.getAllByRole("menuitem")).toHaveLength(3);
    expect(document.activeElement).toHaveTextContent("Erste Aktion");
  });

  it("closes and runs the action when an item is picked", () => {
    const onClose = vi.fn();
    const onSelect = vi.fn();
    render(<Menu items={[{ id: "x", label: "Auswaehlen", onSelect }]} onClose={onClose} />);
    fireEvent.click(screen.getByText("Auswaehlen"));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("arrow keys walk the enabled items and wrap, Escape closes", () => {
    render(<Menu items={ITEMS} onClose={vi.fn()} />);
    fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowDown" });
    expect(document.activeElement).toHaveTextContent("Zweite Aktion");
    // Once around: two enabled items, so the third step lands back on the first.
    fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowDown" });
    expect(document.activeElement).toHaveTextContent("Erste Aktion");
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
  });

  it("keeps header and footer outside the item list", () => {
    render(<Menu items={ITEMS} onClose={() => {}} header={<p>Wer bist du</p>} footer={<p>Ende</p>} />);
    expect(screen.getByText("Wer bist du")).toBeInTheDocument();
    expect(screen.getByText("Ende")).toBeInTheDocument();
    expect(screen.getAllByRole("menuitem")).toHaveLength(3);
  });
});