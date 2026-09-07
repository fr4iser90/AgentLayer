import type { ConversationGoal, ConversationTodo } from "../../lib/api";
import { useTranslation } from "react-i18next";

type Props = {
  goal: ConversationGoal | null;
  disabled?: boolean;
  onPause: () => void;
  onResume: () => void;
  onEdit: () => void;
  onClear: () => void;
};

export function OngoingGoalBar({ goal, disabled, onPause, onResume, onEdit, onClear }: Props) {
  const { t } = useTranslation(["chat"]);
  if (!goal || goal.phase === "completed") return null;
  const paused = goal.phase === "paused";
  const blocked = goal.phase === "blocked";
  return (
    <div className="mb-2 flex items-center gap-2 rounded-lg border border-amber-500/25 bg-amber-950/30 px-3 py-2">
      <span className="text-amber-200/90" aria-hidden>
        ◎
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-amber-200/70">
          {t("chat:ongoingGoal")}
          {paused ? ` · ${t("chat:ongoingGoalPaused")}` : ""}
          {blocked ? ` · ${t("chat:ongoingGoalBlocked")}` : ""}
        </div>
        <p className="truncate text-sm text-neutral-100" title={goal.objective}>
          {goal.objective}
        </p>
        {blocked && goal.blocked_reason ? (
          <p className="truncate text-xs text-rose-300/80" title={goal.blocked_reason}>
            {goal.blocked_reason}
          </p>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {paused ? (
          <button
            type="button"
            className="rounded px-1.5 py-0.5 text-xs text-amber-100 hover:bg-white/10 disabled:opacity-40"
            disabled={disabled}
            onClick={onResume}
            title={t("chat:goalResume")}
          >
            ▶
          </button>
        ) : (
          <button
            type="button"
            className="rounded px-1.5 py-0.5 text-xs text-amber-100 hover:bg-white/10 disabled:opacity-40"
            disabled={disabled || blocked}
            onClick={onPause}
            title={t("chat:goalPause")}
          >
            ❚❚
          </button>
        )}
        <button
          type="button"
          className="rounded px-1.5 py-0.5 text-xs text-amber-100 hover:bg-white/10 disabled:opacity-40"
          disabled={disabled}
          onClick={onEdit}
          title={t("chat:goalEdit")}
        >
          ✎
        </button>
        <button
          type="button"
          className="rounded px-1.5 py-0.5 text-xs text-rose-200 hover:bg-white/10 disabled:opacity-40"
          disabled={disabled}
          onClick={onClear}
          title={t("chat:goalClear")}
        >
          ⌫
        </button>
      </div>
    </div>
  );
}

export function PlanModeBanner({ active }: { active: boolean }) {
  const { t } = useTranslation(["chat"]);
  if (!active) return null;
  return (
    <div className="mb-2 rounded-lg border border-sky-500/30 bg-sky-950/25 px-3 py-1.5 text-xs text-sky-100/90">
      {t("chat:planModeActive")}
    </div>
  );
}

export function ConversationTodosPanel({ todos }: { todos: ConversationTodo[] }) {
  const { t } = useTranslation(["chat"]);
  if (!todos.length) return null;
  const pending = todos.filter((x) => x.status === "pending").length;
  const inProg = todos.filter((x) => x.status === "in_progress").length;
  const done = todos.filter((x) => x.status === "completed").length;
  return (
    <div className="mt-2 rounded-lg border border-white/10 bg-black/25 px-2.5 py-2">
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-surface-muted">
        {t("chat:sessionTodosHeading")} · {inProg} {t("chat:sessionTodosInProgress")} · {pending}{" "}
        {t("chat:sessionTodosPending")}
        {done ? ` · ${done} ${t("chat:sessionTodosDone")}` : ""}
      </div>
      <ul className="space-y-1">
        {todos.map((item) => (
          <li key={item.content} className="flex items-start gap-2 text-xs text-neutral-200">
            <span className="mt-0.5 shrink-0" aria-hidden>
              {item.status === "completed" ? "✓" : item.status === "in_progress" ? "⟳" : "○"}
            </span>
            <span className={item.status === "completed" ? "text-neutral-500 line-through" : ""}>
              {item.content}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
