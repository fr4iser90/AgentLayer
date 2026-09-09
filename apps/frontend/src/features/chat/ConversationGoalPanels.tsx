import type { ConversationGoal, ConversationTodo } from "../../lib/api";
import { useTranslation } from "react-i18next";

type GoalActions = {
  goal: ConversationGoal | null;
  disabled?: boolean;
  onPause: () => void;
  onResume: () => void;
  onEdit: () => void;
  onClear: () => void;
};

const TODO_INLINE_MAX = 6;

function todoGlyph(status: ConversationTodo["status"]): string {
  if (status === "completed") return "✓";
  if (status === "in_progress") return "▶";
  return "○";
}

function GoalActionButtons({
  goal,
  disabled,
  onPause,
  onResume,
  onEdit,
  onClear,
}: GoalActions) {
  const { t } = useTranslation(["chat"]);
  if (!goal || goal.phase === "completed") return null;
  const paused = goal.phase === "paused";
  const blocked = goal.phase === "blocked";
  return (
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
  );
}

/** @deprecated Prefer SessionGoalTodosStrip above the composer. */
export function OngoingGoalBar(props: GoalActions) {
  const { t } = useTranslation(["chat"]);
  const { goal } = props;
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
      <GoalActionButtons {...props} />
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

/** Compact goal + todos strip docked above the composer (web chat primary surface). */
export function SessionGoalTodosStrip({
  goal,
  todos,
  disabled,
  onPause,
  onResume,
  onEdit,
  onClear,
}: GoalActions & { todos: ConversationTodo[] }) {
  const { t } = useTranslation(["chat"]);
  const liveGoal = goal && goal.phase !== "completed" ? goal : null;
  if (!liveGoal && todos.length === 0) return null;

  const paused = liveGoal?.phase === "paused";
  const blocked = liveGoal?.phase === "blocked";
  const done = todos.filter((x) => x.status === "completed").length;
  const visible = todos.slice(0, TODO_INLINE_MAX);
  const overflow = Math.max(0, todos.length - visible.length);
  const rounds =
    liveGoal?.rounds_started != null && liveGoal.max_goal_rounds != null
      ? t("chat:goalRoundChip", {
          round: liveGoal.rounds_started,
          max: liveGoal.max_goal_rounds,
        })
      : null;

  return (
    <div className="mb-2 overflow-hidden rounded-lg border border-amber-500/25 bg-amber-950/25">
      {liveGoal ? (
        <div className="flex items-start gap-2 border-b border-amber-500/15 px-3 py-2">
          <span className="mt-0.5 text-amber-200/90" aria-hidden>
            ◎
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-200/70">
              <span>{t("chat:ongoingGoal")}</span>
              {paused ? <span>· {t("chat:ongoingGoalPaused")}</span> : null}
              {blocked ? <span>· {t("chat:ongoingGoalBlocked")}</span> : null}
              {rounds ? (
                <span className="font-medium normal-case tracking-normal text-amber-100/60">
                  {rounds}
                </span>
              ) : null}
            </div>
            <p className="truncate text-sm text-neutral-100" title={liveGoal.objective}>
              {liveGoal.objective}
            </p>
            {blocked && liveGoal.blocked_reason ? (
              <p className="truncate text-xs text-rose-300/80" title={liveGoal.blocked_reason}>
                {liveGoal.blocked_reason}
              </p>
            ) : null}
          </div>
          <GoalActionButtons
            goal={liveGoal}
            disabled={disabled}
            onPause={onPause}
            onResume={onResume}
            onEdit={onEdit}
            onClear={onClear}
          />
        </div>
      ) : null}
      {todos.length > 0 ? (
        <div className="px-3 py-2">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-amber-200/60">
            {t("chat:sessionTodosHeading")}{" "}
            <span className="font-medium normal-case tracking-normal text-neutral-400">
              {done}/{todos.length}
            </span>
          </div>
          <ul className="flex flex-wrap gap-x-3 gap-y-1">
            {visible.map((item) => (
              <li
                key={`${item.status}:${item.content}`}
                className={`flex min-w-0 max-w-full items-center gap-1.5 text-xs ${
                  item.status === "completed"
                    ? "text-neutral-500 line-through"
                    : item.status === "in_progress"
                      ? "text-amber-100"
                      : "text-neutral-300"
                }`}
                title={item.content}
              >
                <span className="shrink-0" aria-hidden>
                  {todoGlyph(item.status)}
                </span>
                <span className="truncate">{item.content}</span>
              </li>
            ))}
            {overflow > 0 ? (
              <li className="text-xs text-neutral-500">(+{overflow})</li>
            ) : null}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/** @deprecated Prefer SessionGoalTodosStrip above the composer. */
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
              {todoGlyph(item.status)}
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
