import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";

type ContentResponse = {
  content?: { id?: string };
  rag?: { chunk_count?: number };
  detail?: string;
};

function titleFromFilename(name: string): string {
  const base = name.replace(/\.md$/i, "").trim();
  return base.replace(/[-_]+/g, " ").trim() || name;
}

/** Setup wizard: create CMS draft + publish in one step. */
export function OrgKnowledgePublishSection({ onPublished }: { onPublished?: () => void }) {
  const { t } = useTranslation(["org"]);
  const auth = useAuth();
  const deploymentMode = auth.user?.deployment_mode ?? "multi_tenant";
  const base =
    deploymentMode === "agent_system" ? "/v1/admin/tenant-content" : "/v1/org/tenant-content";
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const onFileSelected = useCallback(
    (file: File | undefined) => {
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        const content = typeof reader.result === "string" ? reader.result : "";
        setText(content);
        setTitle((prev) => prev.trim() || titleFromFilename(file.name));
        setMsg(null);
        setErr(null);
      };
      reader.onerror = () => setErr(t("org:knowledgeFileReadFailed"));
      reader.readAsText(file);
    },
    [t]
  );

  const publish = useCallback(async () => {
    const trimmedText = text.trim();
    if (!trimmedText) {
      setErr(t("org:knowledgeTextRequired"));
      setMsg(null);
      return;
    }
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const createRes = await apiFetch(base, auth, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title.trim() || t("org:knowledgeUntitled"),
          body_md: trimmedText,
        }),
      });
      const created = (await createRes.json()) as ContentResponse;
      if (!createRes.ok || !created.content?.id) {
        const detail =
          typeof created.detail === "string" ? created.detail : t("org:knowledgeFailed");
        setErr(detail);
        return;
      }
      const pubRes = await apiFetch(`${base}/${created.content.id}/publish?override=true`, auth, {
        method: "POST",
      });
      const published = (await pubRes.json()) as ContentResponse;
      if (!pubRes.ok) {
        const detail =
          typeof published.detail === "string" ? published.detail : t("org:knowledgeFailed");
        setErr(detail);
        return;
      }
      setMsg(
        t("org:knowledgeSuccess", {
          chunks: published.rag?.chunk_count ?? 0,
          title: title.trim() || t("org:knowledgeUntitled"),
        })
      );
      onPublished?.();
    } catch {
      setErr(t("org:knowledgeFailed"));
    } finally {
      setBusy(false);
    }
  }, [auth, base, onPublished, t, text, title]);

  return (
    <section className="rounded-xl border border-surface-border bg-surface-raised p-5">
      <h2 className="text-sm font-medium text-white">{t("org:knowledgePublishTitle")}</h2>
      <p className="mt-2 text-xs text-surface-muted">{t("org:cmsSetupHint")}</p>

      <div className="mt-4">
        <label className="block text-xs text-surface-muted" htmlFor="org-knowledge-title">
          {t("org:knowledgeTitleLabel")}
        </label>
        <input
          id="org-knowledge-title"
          className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={t("org:knowledgeTitlePlaceholder")}
          autoComplete="off"
        />
      </div>

      <label className="mt-4 block text-xs text-surface-muted" htmlFor="org-knowledge-text">
        {t("org:knowledgeTextLabel")}
      </label>
      <textarea
        id="org-knowledge-text"
        className="mt-1 min-h-48 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={t("org:knowledgeTextPlaceholder")}
      />

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <input
          ref={fileInputRef}
          type="file"
          accept=".md,text/markdown,text/plain"
          className="hidden"
          onChange={(e) => onFileSelected(e.target.files?.[0])}
        />
        <button
          type="button"
          className="rounded-md border border-surface-border px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/5"
          onClick={() => fileInputRef.current?.click()}
        >
          {t("org:knowledgeFileButton")}
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded-md bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          onClick={() => void publish()}
        >
          {busy ? t("org:knowledgePublishing") : t("org:cmsPublish")}
        </button>
      </div>

      {msg ? <p className="mt-3 text-sm text-emerald-400/90">{msg}</p> : null}
      {err ? <p className="mt-3 text-sm text-red-400/90">{err}</p> : null}
    </section>
  );
}
