import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { AuthContextValue } from "../../../auth/AuthContext";
import { fetchAgentConfigFingerprint } from "../agentConfig/agentConfigApi";

type Props = {
  auth: AuthContextValue;
};

/** Read-only harness fingerprint on the benchmark run tab — edit on Harness page. */
export function HarnessRunContextBar({ auth }: Props) {
  const { t } = useTranslation(["admin"]);
  const [fingerprint, setFingerprint] = useState("");
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    if (!auth.accessToken) return;
    setLoading(true);
    try {
      const fp = await fetchAgentConfigFingerprint(auth);
      setFingerprint(String(fp.fingerprint || ""));
    } catch {
      setFingerprint("");
    } finally {
      setLoading(false);
    }
  }, [auth]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <section className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/10 bg-black/20 px-3 py-2">
      <div className="min-w-0">
        <p className="text-[11px] text-surface-muted">{t("admin:benchHarnessContextHint")}</p>
        {loading ? (
          <p className="mt-0.5 text-[10px] text-surface-muted">{t("admin:loading")}</p>
        ) : fingerprint ? (
          <p className="mt-0.5 truncate font-mono text-[10px] text-white/70" title={fingerprint}>
            {fingerprint.slice(0, 40)}…
          </p>
        ) : (
          <p className="mt-0.5 text-[10px] text-surface-muted">—</p>
        )}
      </div>
      <Link
        to="/admin/agent-config"
        className="shrink-0 rounded border border-sky-500/40 bg-sky-950/30 px-2.5 py-1 text-[11px] text-sky-200 hover:bg-sky-950/50"
      >
        {t("admin:benchHarnessContextEdit")}
      </Link>
    </section>
  );

}
