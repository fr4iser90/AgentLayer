/**
 * The area that stops, instead of the app.
 *
 * There was no boundary anywhere in the tree, so one throwing render in one page
 * unmounted the whole shell: white screen, no navigation, no way back except a
 * reload. That is the worst available outcome for a bug that lives in, say, the
 * media panel of a dashboard — the chat next to it was fine.
 *
 * Two properties matter and are easy to get wrong:
 *
 * - **Where it sits.** One boundary around the routed area, not one per widget:
 *   the layout, the navigation and the runtime bar keep working, so the user can
 *   leave the broken page instead of being trapped on it.
 * - **How it lets go.** A boundary that has caught stays caught — React gives it
 *   no reason to retry. Without `resetKey`, a crash on `/chat` would keep showing
 *   the fallback after navigating to `/settings`, because the boundary itself
 *   never unmounted. The route is passed in and any change clears the error.
 *
 * The message is shown as it is. It is the one sentence that tells the user and
 * whoever they report it to what actually broke, and a generic "something went
 * wrong" throws that away while hiding nothing that a stack trace does not.
 */
import { Component, type ErrorInfo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "./Button";
import { EmptyState } from "./EmptyState";

export interface ErrorBoundaryProps {
  children: ReactNode;
  /** What to call the broken area — it lands in the console line next to the stack. */
  area: string;
  /** Change this to let go of the crash. Pass the route. */
  resetKey?: string;
  /** Replace the fallback for one boundary. Called with the error and the reset. */
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface State {
  error: Error | null;
  resetKey?: string;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, State> {
  state: State;

  constructor(props: ErrorBoundaryProps) {
    super(props);
    // The key starts at the value the boundary was mounted with. Left `undefined`,
    // the comparison below sees a change on every mount that has a key and clears
    // the error React has just caught — React then retries the throwing render and,
    // after repeating it, takes the root down instead of the area.
    this.state = { error: null, resetKey: props.resetKey };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  static getDerivedStateFromProps(props: ErrorBoundaryProps, state: State): Partial<State> | null {
    if (state.error !== null && props.resetKey !== state.resetKey) {
      return { error: null, resetKey: props.resetKey };
    }
    return null;
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Re-thrown to the console on purpose: the fallback is what the user sees, and
    // it cannot carry a stack. Without this line the crash is invisible to debug.
    console.error(`[ErrorBoundary] ${this.props.area}`, error, info.componentStack);
  }

  reset = () => {
    this.setState({ error: null });
  };

  render() {
    const { error } = this.state;
    if (error === null) return this.props.children;
    if (this.props.fallback) return this.props.fallback(error, this.reset);
    return <BoundaryFallback area={this.props.area} error={error} onRetry={this.reset} />;
  }
}

export interface BoundaryFallbackProps {
  area: string;
  error: Error;
  onRetry: () => void;
}

/** The default face of a caught crash: the mascot that means "overheated", one action. */
export function BoundaryFallback({ area, error, onRetry }: BoundaryFallbackProps) {
  const { t } = useTranslation("common");
  return (
    <div data-error-boundary={area}>
      <EmptyState
        pose="error"
        title={t("errorBoundary.title")}
        hint={error.message || t("errorBoundary.hint")}
        action={
          <Button variant="primary" onClick={onRetry}>
            {t("errorBoundary.retry")}
          </Button>
        }
      />
    </div>
  );
}