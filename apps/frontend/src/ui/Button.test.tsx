import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Button, buttonClass } from "./Button";

/**
 * The tests here assert on the class string, not on rendered CSS. Tailwind
 * resolves a duplicated property by generated stylesheet order rather than by
 * the order in the attribute, so jsdom cannot tell whether a call site won a
 * collision — the only defence is that the primitive never emits two utilities
 * for the same property in the first place. That is what "must not contain"
 * assertions check.
 */
describe("ui/Button", () => {
  it("is type=button unless told otherwise", () => {
    render(<Button>Speichern</Button>);
    // A `<button>` without `type` submits the surrounding form, and most of the
    // app's buttons sit in one.
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });

  it("forwards an explicit type", () => {
    render(
      <Button type="submit" variant="primary">
        Anmelden
      </Button>
    );
    expect(screen.getByRole("button")).toHaveAttribute("type", "submit");
  });

  it("puts dark ink on a filled variant, whatever the hue", () => {
    for (const tone of ["accent", "success", "warning", "danger"] as const) {
      render(
        <Button variant="primary" tone={tone}>
          {tone}
        </Button>
      );
      const cls = screen.getAllByRole("button").at(-1)?.className ?? "";
      expect(cls).toContain("text-ink-on-fill");
      expect(cls).not.toMatch(/\btext-white\b/);
    }
  });

  it("keeps destructive outlined unless a tone fills it", () => {
    render(<Button variant="danger">Löschen</Button>);
    const cls = screen.getByRole("button").className;
    expect(cls).toContain("border-danger");
    expect(cls).toContain("bg-transparent");
  });

  it("sizes by the token pair and nothing else", () => {
    render(<Button size="sm">k</Button>);
    expect(screen.getByRole("button").className).toContain("h-7");
  });

  it("makes an icon-only button as wide as it is tall", () => {
    render(
      <Button square size="sm" aria-label="Schliessen">
        ×
      </Button>
    );
    const cls = screen.getByRole("button").className;
    expect(cls).toContain("h-7");
    expect(cls).toContain("w-7");
    expect(cls).toContain("p-0");
    expect(cls).not.toContain("px-firm");
  });

  it("releases the content box for a block surface", () => {
    render(
      <Button block variant="plain">
        Kopfzeile
      </Button>
    );
    const cls = screen.getByRole("button").className;
    expect(cls).toContain("text-left");
    // The call site spreads its own content (`justify-between`, `flex-col`) and
    // sizes itself (`min-h-[…]`); centring or a fixed height here would lose to
    // Tailwind's order and clip the panel.
    expect(cls).not.toContain("justify-center");
    expect(cls).not.toMatch(/\bh-\d/);
    expect(cls).not.toContain("whitespace-nowrap");
  });

  it("paints nothing on a plain surface", () => {
    const cls = buttonClass("plain", "md", undefined, "accent", false, true);
    // The migrated surfaces bring their own background, border and radius. A
    // second `background` from the variant would make the stylesheet, not the
    // call site, decide the colour.
    expect(cls).not.toMatch(/\bbg-/);
    expect(cls).not.toMatch(/\bborder\b/);
    expect(cls).not.toMatch(/\brounded-/);
    // What they were missing is still there.
    expect(cls).toContain("focus-visible:shadow-focus");
    expect(cls).toContain("disabled:opacity-45");
  });

  it("still gives a plain surface its focus ring and disabled state", () => {
    render(
      <Button variant="plain" block disabled>
        Gesperrt
      </Button>
    );
    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
    expect(button.className).toContain("disabled:pointer-events-none");
  });

  it("appends the caller's classes without replacing the variant", () => {
    render(
      <Button variant="primary" className="mt-base">
        Weiter
      </Button>
    );
    const cls = screen.getByRole("button").className;
    expect(cls).toContain("mt-base");
    expect(cls).toContain("bg-accent");
  });

  it("renders its children and handles clicks", () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Öffnen</Button>);
    fireEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});