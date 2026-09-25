/**
 * Transient and critical notifications.
 *
 * Before this existed the app had 410 `catch` blocks, 48 of which swallowed
 * their error with no UI and no log, and zero toast/snackbar/notification
 * surface of any kind. A failed `putConversation()` left the message on screen
 * from local state and absent from the server — the user could not tell that
 * reloading would delete what they had just written.
 *
 * The six error classes this primitive serves are a decision about VISIBILITY,
 * not about colour: transient (3 s, gone) and critical (persistent banner until
 * resolved) are the two ends, and picking the wrong end is the bug — a warning
 * that vanishes while unread, or a routine confirmation that never leaves.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Check, Info, X } from "lucide-react";

export type ToastTone = "info" | "success" | "warning" | "danger";

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastInput {
  title: string;
  body?: string;
  tone?: ToastTone;
  /**
   * Auto-dismiss delay. `null` makes the toast persistent — it stays until the
   * user dismisses it or the action resolves it. Use for anything the user
   * could lose data over; do not use it to make a routine confirmation
   * harder to get rid of.
   */
  durationMs?: number | null;
  action?: ToastAction;
  /**
   * Also raise the persistent top banner. For the critical class only: a
   * session that expired or a bridge that dropped has to stay on screen while
   * the user works, not just for three seconds.
   */
  banner?: boolean;
}

interface ToastItem extends Required<Pick<ToastInput, "title" | "tone" | "durationMs">> {
  id: number;
  body?: string;
  action?: ToastAction;
  banner: boolean;
}

/** Three at a time: past that the stack itself becomes the thing to read. */
export const MAX_TRANSIENT = 3;
export const DEFAULT_DURATION_MS = 3000;

const TONE_CLASSES: Record<ToastTone, string> = {
  info: "border-line bg-card text-ink-primary",
  success: "border-success/40 bg-card text-ink-primary",
  warning: "border-warning/45 bg-card text-ink-primary",
  danger: "border-danger/50 bg-card text-ink-primary",
};

const ICON_TONE: Record<ToastTone, string> = {
  info: "text-accent",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
};

function ToastIcon({ tone }: { tone: ToastTone }) {
  if (tone === "danger" || tone === "warning") {
    return <AlertTriangle size={16} aria-hidden className={`shrink-0 ${ICON_TONE[tone]}`} />;
  }
  if (tone === "success") {
    return <Check size={16} aria-hidden className={`shrink-0 ${ICON_TONE[tone]}`} />;
  }
  return <Info size={16} aria-hidden className={`shrink-0 ${ICON_TONE[tone]}`} />;
}

interface ToastApi {
  push: (input: ToastInput) => number;
  dismiss: (id: number) => void;
  info: (title: string, body?: string) => number;
  success: (title: string, body?: string) => number;
  warning: (title: string, body?: string) => number;
  /** Persistent by default: the user has to acknowledge it. */
  danger: (title: string, body?: string) => number;
  /** Persistent toast plus the top banner. */
  critical: (title: string, body?: string) => number;
}

const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) {
    throw new Error("useToast must be used inside <ToastProvider>");
  }
  return api;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation("common");
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const push = useCallback((input: ToastInput): number => {
    const id = nextId.current;
    nextId.current += 1;
    const item: ToastItem = {
      id,
      title: input.title,
      body: input.body,
      tone: input.tone ?? "info",
      durationMs: input.durationMs === undefined ? DEFAULT_DURATION_MS : input.durationMs,
      action: input.action,
      banner: input.banner ?? false,
    };
    setItems((current) => {
      // Only transient toasts are capped. Dropping a persistent one to make
      // room for a confirmation would discard exactly the notice that must
      // not be lost.
      const transient = current.filter((entry) => entry.durationMs !== null);
      if (item.durationMs === null || transient.length < MAX_TRANSIENT) {
        return [...current, item];
      }
      const oldest = transient[0];
      return [...current.filter((entry) => entry.id !== oldest.id), item];
    });
    return id;
  }, []);

  // Arm timers from the rendered list rather than inside `push`, so a toast
  // replaced before it ever painted never leaves a timer behind.
  useEffect(() => {
    const live = new Set(items.map((item) => item.id));
    for (const [id, timer] of timers.current) {
      if (!live.has(id)) {
        clearTimeout(timer);
        timers.current.delete(id);
      }
    }
    for (const item of items) {
      if (item.durationMs === null || timers.current.has(item.id)) continue;
      timers.current.set(
        item.id,
        setTimeout(() => dismiss(item.id), item.durationMs)
      );
    }
  }, [items, dismiss]);

  useEffect(
    () => () => {
      for (const timer of timers.current.values()) clearTimeout(timer);
      timers.current.clear();
    },
    []
  );

  /**
   * Pause on hover and on focus. A toast that expires while the pointer is
   * over it — or while a keyboard user is reading it — is a timer the user
   * cannot control, which is the failure WCAG 2.2.1 is about.
   */
  const pause = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const resume = useCallback(
    (id: number) => {
      if (timers.current.has(id)) return;
      const item = items.find((entry) => entry.id === id);
      if (!item || item.durationMs === null) return;
      timers.current.set(id, setTimeout(() => dismiss(id), item.durationMs));
    },
    [items, dismiss]
  );

  const api = useMemo<ToastApi>(
    () => ({
      push,
      dismiss,
      info: (title, body) => push({ title, body, tone: "info" }),
      success: (title, body) => push({ title, body, tone: "success" }),
      warning: (title, body) => push({ title, body, tone: "warning" }),
      danger: (title, body) => push({ title, body, tone: "danger", durationMs: null }),
      critical: (title, body) =>
        push({ title, body, tone: "danger", durationMs: null, banner: true }),
    }),
    [push, dismiss]
  );

  const banners = items.filter((item) => item.banner);
  const stack = items.filter((item) => !item.banner);

  return (
    <ToastContext.Provider value={api}>
      {children}
      {typeof document === "undefined"
        ? null
        : createPortal(
            <>
              {banners.length > 0 ? (
                <div
                  role="region"
                  aria-label={t("toast.bannerRegion")}
                  className="pointer-events-none fixed inset-x-0 top-0 z-toast flex flex-col gap-hair"
                >
                  {banners.map((item) => (
                    <div
                      key={item.id}
                      role="alert"
                      className={[
                        "pointer-events-auto mx-auto mt-base flex w-full max-w-page items-start gap-soft",
                        "animate-toast-in rounded-card border px-soft py-soft shadow-overlay",
                        TONE_CLASSES[item.tone],
                      ].join(" ")}
                    >
                      <ToastIcon tone={item.tone} />
                      <div className="min-w-0 flex-1">
                        <p className="text-body font-medium">{item.title}</p>
                        {item.body ? (
                          <p className="mt-hair text-label text-ink-secondary">{item.body}</p>
                        ) : null}
                      </div>
                      {item.action ? (
                        <button
                          type="button"
                          onClick={() => {
                            item.action?.onClick();
                            dismiss(item.id);
                          }}
                          className="shrink-0 rounded-tile px-base py-tight text-label font-medium text-accent hover:bg-accent-subtle"
                        >
                          {item.action.label}
                        </button>
                      ) : null}
                      <button
                        type="button"
                        aria-label={t("toast.dismiss")}
                        onClick={() => dismiss(item.id)}
                        className="shrink-0 rounded-tile p-tight text-ink-muted hover:bg-white/10 hover:text-ink-primary"
                      >
                        <X size={14} aria-hidden />
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}
              <div
                role="region"
                aria-label={t("toast.region")}
                className="pointer-events-none fixed bottom-wide right-wide z-toast flex w-full max-w-dialog flex-col-reverse gap-soft"
              >
                {stack.map((item) => (
                  <div
                    key={item.id}
                    role={item.tone === "danger" ? "alert" : "status"}
                    aria-live={item.tone === "danger" ? "assertive" : "polite"}
                    onMouseEnter={() => pause(item.id)}
                    onMouseLeave={() => resume(item.id)}
                    onFocusCapture={() => pause(item.id)}
                    onBlurCapture={() => resume(item.id)}
                    className={[
                      "pointer-events-auto flex items-start gap-soft animate-toast-in",
                      "rounded-card border px-soft py-soft shadow-overlay",
                      TONE_CLASSES[item.tone],
                    ].join(" ")}
                  >
                    <ToastIcon tone={item.tone} />
                    <div className="min-w-0 flex-1">
                      <p className="text-body font-medium">{item.title}</p>
                      {item.body ? (
                        <p className="mt-hair text-label text-ink-secondary">{item.body}</p>
                      ) : null}
                    </div>
                    {item.action ? (
                      <button
                        type="button"
                        onClick={() => {
                          item.action?.onClick();
                          dismiss(item.id);
                        }}
                        className="shrink-0 rounded-tile px-base py-tight text-label font-medium text-accent hover:bg-accent-subtle"
                      >
                        {item.action.label}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      aria-label={t("toast.dismiss")}
                      onClick={() => dismiss(item.id)}
                      className="shrink-0 rounded-tile p-tight text-ink-muted hover:bg-white/10 hover:text-ink-primary"
                    >
                      <X size={14} aria-hidden />
                    </button>
                  </div>
                ))}
              </div>
            </>,
            document.body
          )}
    </ToastContext.Provider>
  );
}