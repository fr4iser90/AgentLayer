import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import type { BenchmarkScenarioResult } from "./benchmarksApi";
import { copyScenarioDetailsToClipboard } from "./benchCopyDetails";

export function CopyScenarioDetailsButton({
  res,
  compact = false,
  className = "",
}: {
  res: BenchmarkScenarioResult;
  compact?: boolean;
  className?: string;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);

  const onClick = useCallback(
    async (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setFailed(false);
      try {
        await copyScenarioDetailsToClipboard(res);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 2000);
      } catch {
        setFailed(true);
        window.setTimeout(() => setFailed(false), 2500);
      }
    },
    [res],
  );

  const label = copied
    ? t("admin:benchDetailCopied")
    : failed
      ? t("admin:benchDetailCopyFailed")
      : t("admin:benchDetailCopyDetails");

  return (
    <button
      type="button"
      className={
        className ||
        (compact
          ? "rounded px-1 text-[10px] text-surface-muted hover:bg-white/5 hover:text-sky-300"
          : "rounded border border-white/10 px-2 py-0.5 text-[11px] text-surface-muted hover:border-sky-500/30 hover:text-sky-300")
      }
      title={label}
      aria-label={label}
      onClick={(e) => void onClick(e)}
    >
      {copied ? "✓" : failed ? "!" : compact ? "⎘" : label}
    </button>
  );
}
