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
    <section className="flex flex-wrap items-center justify-between gap-soft rounded-card border border-line bg-black/20 px-soft py-base">
      <div className="min-w-0">
        <p className="text-meta text-ink-muted">{t("admin:benchHarnessContextHint")}</p>
        {loading ? (
          <p className="mt-hair text-meta text-ink-muted">{t("admin:loading")}</p>
        ) : fingerprint ? (
          <p className="mt-hair truncate font-mono text-meta text-white/70" title={fingerprint}>
            {fingerprint.slice(0, 40)}…
          </p>
        ) : (
          <p className="mt-hair text-meta text-ink-muted">—</p>
        )}
      </div>
      <Link
        to="/admin/agent-config"
        className="shrink-0 rounded-tile border border-accent/40 bg-accent-subtle px-firm py-tight text-meta text-badge-accent hover:bg-accent-subtle"
      >
        {t("admin:benchHarnessContextEdit")}
      </Link>
    </section>
  );

}
