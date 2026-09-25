/**
 * Toast access from outside React.
 *
 * Two of the things this primitive exists to report cannot reach a hook:
 *
 * - `lib/api.ts` runs the token refresh and has to say "your session expired"
 *   when it fails. It is a plain module, called from other plain modules.
 * - The nine `putConversation()` calls in `ChatPage` sit inside `setState`
 *   updater callbacks, where a hook cannot be called either.
 *
 * Without a surface at all, both currently end in a swallowed error. A bus that
 * no-ops before the provider mounts is deliberate: a module-level fetch failing
 * during boot must not throw on its way past a UI that does not exist yet.
 *
 * `once` exists because a flaky network does not produce one failure, it
 * produces thirty in a row, and thirty identical toasts is worse than none —
 * the user reads the stack, not the message.
 */
import type { ToastApi, ToastInput } from "./Toast";

let api: ToastApi | null = null;
const openByKey = new Map<string, number>();

export function registerToastApi(next: ToastApi): () => void {
  api = next;
  return () => {
    if (api === next) api = null;
    openByKey.clear();
  };
}

export const toast = {
  push(input: ToastInput): number | null {
    return api ? api.push(input) : null;
  },
  info(title: string, body?: string) {
    api?.info(title, body);
  },
  success(title: string, body?: string) {
    api?.success(title, body);
  },
  warning(title: string, body?: string) {
    api?.warning(title, body);
  },
  danger(title: string, body?: string) {
    api?.danger(title, body);
  },
  critical(title: string, body?: string) {
    api?.critical(title, body);
  },

  /**
   * Show at most one toast per `key` until `settle(key)` runs. Returns true if
   * this call was the one that surfaced.
   */
  once(key: string, build: (retry: () => void) => ToastInput, retry?: () => void): boolean {
    if (!api || openByKey.has(key)) return false;
    const id = api.push(build(() => retry?.()));
    openByKey.set(key, id);
    return true;
  },

  /** Called when the condition behind a `once` toast goes away. */
  settle(key: string): void {
    const id = openByKey.get(key);
    if (id === undefined) return;
    openByKey.delete(key);
    api?.dismiss(id);
  },
};