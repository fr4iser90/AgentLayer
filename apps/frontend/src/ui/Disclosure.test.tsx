import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Disclosure } from "./Disclosure";

describe("ui/Disclosure", () => {
  it("hides the body until the trigger is pressed and reports the state", () => {
    render(
      <Disclosure title="Eingebetteter Kontext">
        <p>Der ausgeblendete Text</p>
      </Disclosure>
    );
    const trigger = screen.getByRole("button", { name: /Eingebetteter Kontext/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Der ausgeblendete Text")).not.toBeInTheDocument();
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Der ausgeblendete Text")).toBeInTheDocument();
  });

  it("points aria-controls at the panel it reveals", () => {
    render(
      <Disclosure title="Gruppe" defaultOpen>
        <p>Text</p>
      </Disclosure>
    );
    const controls = screen.getByRole("button").getAttribute("aria-controls");
    expect(controls).toBeTruthy();
    expect(document.getElementById(controls as string)).toHaveTextContent("Text");
  });

  it("swaps the hint word with the state instead of hiding it", () => {
    render(
      <Disclosure title="Kontext" hint={{ open: "Zuklappen", closed: "Aufklappen" }}>
        <p>Text</p>
      </Disclosure>
    );
    expect(screen.getByText("Aufklappen")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Zuklappen")).toBeInTheDocument();
    expect(screen.queryByText("Aufklappen")).not.toBeInTheDocument();
  });

  it("can be driven from outside and reports changes", () => {
    const onOpenChange = vi.fn();
    const view = render(
      <Disclosure title="Filter" open={false} onOpenChange={onOpenChange}>
        <p>Text</p>
      </Disclosure>
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onOpenChange).toHaveBeenCalledWith(true);
    // The parent did not change the prop, so nothing opened: a controlled
    // disclosure must not open itself behind its owner's back.
    expect(screen.queryByText("Text")).not.toBeInTheDocument();
    view.rerender(
      <Disclosure title="Filter" open onOpenChange={onOpenChange}>
        <p>Text</p>
      </Disclosure>
    );
    expect(screen.getByText("Text")).toBeInTheDocument();
  });
});