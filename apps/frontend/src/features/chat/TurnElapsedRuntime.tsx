import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

function formatElapsed(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  const min = Math.floor(ms / 60_000);
  const sec = Math.floor((ms % 60_000) / 1000);
  return sec > 0 ? `${min} min ${sec} s` : `${min} min`;
}

type Props = {
  startedAtMs: number;
  className?: string;
};

/** Elapsed wall time for the in-flight assistant turn (Laufzeit in der Message). */
export function TurnElapsedRuntime({ startedAtMs, className = "" }: Props) {
  const { t } = useTranslation(["chat"]);
  const [elapsedMs, setElapsedMs] = useState(() => Math.max(0, Date.now() - startedAtMs));

  useEffect(() => {
    const tick = () => setElapsedMs(Math.max(0, Date.now() - startedAtMs));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startedAtMs]);

  return (
    <p className={`tabular-nums text-[10px] text-neutral-400 ${className}`}>
      <span className="font-semibold uppercase tracking-wide text-surface-muted">
        {t("chat:messageRuntimeLabel")}{" "}
      </span>
      {formatElapsed(elapsedMs)}
    </p>
  );
}
