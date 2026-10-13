import type { ReactNode } from "react";
import type { ConversationGoal, ConversationTodo } from "../../lib/api";
import { useTranslation } from "react-i18next";
import { Check, Circle, Pause, Pencil, Play, X } from "lucide-react";
import { Tooltip } from "../../ui/Tooltip";
import { Button } from "../../ui/Button";

type GoalActions = {
  goal: ConversationGoal | null;
  disabled?: boolean;
  onPause: () => void;
  onResume: () => void;
  onEdit: () => void;
  onClear: () => void;
};

const TODO_INLINE_MAX = 6;

function todoGlyph(status: ConversationTodo["status"]): ReactNode {
  if (status === "completed") return <Check className="h-3.5 w-3.5" />;
  if (status === "in_progress") return <Play className="h-3.5 w-3.5" />;
  return <Circle className="h-3.5 w-3.5" />;
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
    <div className="flex shrink-0 items-center gap-tight">
      {paused ? (
        <Tooltip label={t("chat:goalResume")}>
        <Button
          variant="ghost"
          size="sm"
            type="button"
            className="px-snug py-hair text-xs text-badge-warning hover:bg-white/10"
            disabled={disabled}
            onClick={onResume}
        >
            <Play aria-hidden className="h-3.5 w-3.5" />
          </Button>
        </Tooltip>
      ) : (
        <Tooltip label={t("chat:goalPause")}>
        <Button
          variant="ghost"
          size="sm"
            type="button"
            className="px-snug py-hair text-xs text-badge-warning hover:bg-white/10"
            disabled={disabled || blocked}
            onClick={onPause}
        >
            <Pause aria-hidden className="h-3.5 w-3.5" />
          </Button>
        </Tooltip>
      )}
      <Tooltip label={t("chat:goalEdit")}>
      <Button
        variant="ghost"
        size="sm"
          type="button"
          className="px-snug py-hair text-xs text-badge-warning hover:bg-white/10"
          disabled={disabled}
          onClick={onEdit}
      >
          <Pencil aria-hidden className="h-3.5 w-3.5" />
        </Button>
      </Tooltip>
      <Tooltip label={t("chat:goalClear")}>
      <Button
        variant="ghost"
        size="sm"
          type="button"
          className="px-snug py-hair text-xs text-badge-danger hover:bg-white/10"
          disabled={disabled}
          onClick={onClear}
      >
          <X aria-hidden className="h-3.5 w-3.5" />
        </Button>
      </Tooltip>
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
    <div className="mb-base flex items-center gap-base rounded-card border border-warning/25 bg-warning-subtle px-soft py-base">
      <span className="text-badge-warning" aria-hidden>
        ◎
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-meta font-semibold uppercase tracking-wide text-badge-warning">
          {t("chat:ongoingGoal")}
          {paused ? ` · ${t("chat:ongoingGoalPaused")}` : ""}
          {blocked ? ` · ${t("chat:ongoingGoalBlocked")}` : ""}
        </div>
        <p className="truncate text-sm text-ink-primary" title={goal.objective}>
          {goal.objective}
        </p>
        {blocked && goal.blocked_reason ? (
          <p className="truncate text-xs text-danger/80" title={goal.blocked_reason}>
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
    <div className="mb-base rounded-card border border-accent/30 bg-accent-subtle px-soft py-snug text-xs text-badge-accent">
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
    <div className="mb-base overflow-hidden rounded-card border border-warning/25 bg-warning-subtle">
      {liveGoal ? (
        <div className="flex items-start gap-base border-b border-warning/15 px-soft py-base">
          <span className="mt-hair text-badge-warning" aria-hidden>
            ◎
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-base gap-y-hair text-meta font-semibold uppercase tracking-wide text-badge-warning">
              <span>{t("chat:ongoingGoal")}</span>
              {paused ? <span>· {t("chat:ongoingGoalPaused")}</span> : null}
              {blocked ? <span>· {t("chat:ongoingGoalBlocked")}</span> : null}
              {rounds ? (
                <span className="font-medium normal-case tracking-normal text-badge-warning">
                  {rounds}
                </span>
              ) : null}
            </div>
            <p className="truncate text-sm text-ink-primary" title={liveGoal.objective}>
              {liveGoal.objective}
            </p>
            {blocked && liveGoal.blocked_reason ? (
              <p className="truncate text-xs text-danger/80" title={liveGoal.blocked_reason}>
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
        <div className="px-soft py-base">
          <div className="mb-tight text-meta font-semibold uppercase tracking-wide text-badge-warning">
            {t("chat:sessionTodosHeading")}{" "}
            <span className="font-medium normal-case tracking-normal text-ink-muted">
              {done}/{todos.length}
            </span>
          </div>
          <ul className="flex flex-wrap gap-x-soft gap-y-tight">
            {visible.map((item) => (
              <li
                key={`${item.status}:${item.content}`}
                className={`flex min-w-0 max-w-full items-center gap-snug text-xs ${
                  item.status === "completed"
                    ? "text-ink-muted line-through"
                    : item.status === "in_progress"
                      ? "text-badge-warning"
                      : "text-ink-secondary"
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
              <li className="text-xs text-ink-muted">(+{overflow})</li>
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
    <div className="mt-base rounded-card border border-line bg-black/25 px-firm py-base">
      <div className="mb-snug text-meta font-semibold uppercase tracking-wide text-ink-muted">
        {t("chat:sessionTodosHeading")} · {inProg} {t("chat:sessionTodosInProgress")} · {pending}{" "}
        {t("chat:sessionTodosPending")}
        {done ? ` · ${done} ${t("chat:sessionTodosDone")}` : ""}
      </div>
      <ul className="space-y-tight">
        {todos.map((item) => (
          <li key={item.content} className="flex items-start gap-base text-xs text-ink-primary">
            <span className="mt-hair shrink-0" aria-hidden>
              {todoGlyph(item.status)}
            </span>
            <span className={item.status === "completed" ? "text-ink-muted line-through" : ""}>
              {item.content}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
