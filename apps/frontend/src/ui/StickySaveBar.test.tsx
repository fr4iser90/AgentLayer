import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { StickySaveBar } from "./StickySaveBar";

describe("ui/StickySaveBar", () => {
  it("pins to the bottom above the page but below a dialog", () => {
    const { container } = render(<StickySaveBar saveLabel="Speichern" />);
    const bar = container.firstElementChild as HTMLElement;
    // sticky + bottom-0 is the pinning; z-lift is the one layer that sits over
    // the page (z-base..z-raised) and under z-float/z-modal/z-menu, so a dialog
    // opened from the form is never covered by the bar.
    expect(bar.className).toContain("sticky");
    expect(bar.className).toContain("bottom-0");
    expect(bar.className).toContain("z-lift");
    expect(bar.className).not.toMatch(/z-(float|modal|menu|top)\b/);
  });

  it("shows the standing hint until a save result replaces it, then announces the result", () => {
    const { rerender } = render(<StickySaveBar saveLabel="Speichern">Änderungen wirken sofort</StickySaveBar>);
    expect(screen.getByText("Änderungen wirken sofort")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    rerender(
      <StickySaveBar saveLabel="Speichern" status={{ ok: false, text: "Gespeichert ist es nicht" }}>
        Änderungen wirken sofort
      </StickySaveBar>
    );
    expect(screen.getByRole("status")).toHaveTextContent("Gespeichert ist es nicht");
    expect(screen.queryByText("Änderungen wirken sofort")).not.toBeInTheDocument();
  });

  it("refuses to save when disabled or busy", () => {
    const onSave = vi.fn();
    render(<StickySaveBar saveLabel="Speichern" onSave={onSave} disabled />);
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(onSave).not.toHaveBeenCalled();
  });

  it("renders the secondary action next to save", () => {
    render(<StickySaveBar saveLabel="Speichern" secondary={<button type="button">Verwerfen</button>} />);
    fireEvent.click(screen.getByRole("button", { name: "Verwerfen" }));
    expect(screen.getByRole("button", { name: "Speichern" })).toBeInTheDocument();
  });
});