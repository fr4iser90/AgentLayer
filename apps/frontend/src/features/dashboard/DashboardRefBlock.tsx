import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import type { UiBlock } from "./types";
import { DashboardBlockTile } from "./DashboardBlocks";

type RenderPayload = {
  block: UiBlock;
  data: Record<string, unknown>;
  source_title?: string;
  source_kind?: string;
};

export function DashboardRefBlockBody(props: {
  block: UiBlock;
  readOnly: boolean;
}) {
  const { t } = useTranslation(["dashboard"]);
  const auth = useAuth();
  const p = props.block.props;
  const sourceId = String(p.sourceDashboardId || "").trim();
  const sourceBlockId = String(p.sourceBlockId || "").trim();
  const [payload, setPayload] = useState<RenderPayload | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!sourceId || !sourceBlockId) {
      setErr(t("dashboard:refMissingSource"));
      return;
    }
    setLoading(true);
    setErr(null);
    try {
      const res = await apiFetch(
        `/v1/dashboards/${sourceId}/blocks/${encodeURIComponent(sourceBlockId)}/render`,
        auth,
      );
      const raw = await res.text();
      if (!res.ok) {
        setErr(raw || t("dashboard:refLoadFailed"));
        setPayload(null);
        return;
      }
      const j = JSON.parse(raw) as RenderPayload & { ok?: boolean };
      setPayload({
        block: j.block as UiBlock,
        data: (j.data as Record<string, unknown>) || {},
        source_title: j.source_title,
        source_kind: j.source_kind,
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("dashboard:refLoadFailed"));
    } finally {
      setLoading(false);
    }
  }, [auth, sourceBlockId, sourceId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !payload) {
    return <p className="text-sm text-surface-muted">{t("dashboard:refLoading")}</p>;
  }
  if (err) {
    return (
      <div className="space-y-2 text-sm">
        <p className="text-amber-300">{err}</p>
        <button type="button" className="text-sky-400 hover:underline" onClick={() => void load()}>
          {t("dashboard:refRetry")}
        </button>
      </div>
    );
  }
  if (!payload?.block) {
    return <p className="text-sm text-surface-muted">{t("dashboard:refEmpty")}</p>;
  }

  const noop = () => {};

  return (
    <div className="space-y-2">
      {p.sourceLabel || payload.source_title ? (
        <p className="text-[10px] uppercase tracking-wide text-surface-muted">
          {t("dashboard:refFrom", {
            title: String(p.sourceLabel || payload.source_title),
          })}
        </p>
      ) : null}
      <DashboardBlockTile
        block={payload.block}
        data={payload.data}
        setData={noop}
        readOnly
        dashboardId={sourceId}
      />
    </div>
  );
}
