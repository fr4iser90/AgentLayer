/**
 * Tabs with the semantics the hand-rolled versions left out.
 *
 * Seven files had a tab strip. Three different idioms marked the active tab and
 * only two of the seven declared `role="tablist"` — so five strips were not
 * recognisable as tabs to assistive tech, and none of them responded to the
 * arrow keys that the tab pattern is defined by (WCAG 2.1.1 / ARIA tabs).
 */
import { useRef } from "react";
import { useId } from "react";

export interface TabItem {
  id: string;
  label: string;
  disabled?: boolean;
}

export interface TabsProps {
  items: TabItem[];
  value: string;
  onChange: (id: string) => void;
  ariaLabel: string;
  className?: string;
  /**
   * id shared with the `TabPanel`s this strip drives. Without it the strip
   * cannot name panels it has never seen, so it omits `aria-controls` rather
   * than pointing at an element that is not there.
   */
  groupId?: string;
}

export function Tabs({ items, value, onChange, ariaLabel, className, groupId }: TabsProps) {
  const autoGroup = useId();
  const group = groupId ?? autoGroup;
  const refs = useRef(new Map<string, HTMLButtonElement>());

  const move = (from: string, delta: number) => {
    const enabled = items.filter((item) => !item.disabled);
    if (enabled.length === 0) return;
    const index = enabled.findIndex((item) => item.id === from);
    const next = enabled[(index + delta + enabled.length) % enabled.length];
    onChange(next.id);
    refs.current.get(next.id)?.focus();
  };

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={[
        "flex flex-wrap items-center gap-hair border-b border-line",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      onKeyDown={(event) => {
        if (event.key === "ArrowRight") {
          event.preventDefault();
          move(value, 1);
        } else if (event.key === "ArrowLeft") {
          event.preventDefault();
          move(value, -1);
        } else if (event.key === "Home") {
          event.preventDefault();
          const first = items.find((item) => !item.disabled);
          if (first) {
            onChange(first.id);
            refs.current.get(first.id)?.focus();
          }
        } else if (event.key === "End") {
          event.preventDefault();
          const last = [...items].reverse().find((item) => !item.disabled);
          if (last) {
            onChange(last.id);
            refs.current.get(last.id)?.focus();
          }
        }
      }}
    >
      {items.map((item) => {
        const selected = item.id === value;
        return (
          <button
            key={item.id}
            ref={(el) => {
              if (el) refs.current.set(item.id, el);
              else refs.current.delete(item.id);
            }}
            type="button"
            role="tab"
            id={`${group}-${item.id}`}
            aria-selected={selected}
            aria-controls={groupId ? `${group}-panel-${item.id}` : undefined}
            tabIndex={selected ? 0 : -1}
            disabled={item.disabled}
            onClick={() => onChange(item.id)}
            className={[
              "rounded-tile px-soft py-base text-body transition-colors",
              "focus-visible:outline-none focus-visible:shadow-focus",
              "disabled:pointer-events-none disabled:opacity-45",
              selected
                ? "bg-white/10 text-ink-primary"
                : "text-ink-muted hover:bg-white/5 hover:text-ink-primary",
            ].join(" ")}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

/** Pair a content region with a `Tabs` strip that was given the same `group`. */
export function TabPanel({
  id,
  group,
  children,
  className,
}: {
  id: string;
  group: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      role="tabpanel"
      id={`${group}-panel-${id}`}
      aria-labelledby={`${group}-${id}`}
      tabIndex={0}
      className={className}
    >
      {children}
    </div>
  );
}