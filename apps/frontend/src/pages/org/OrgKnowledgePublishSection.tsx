import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { hasOrgSurface } from "../../auth/deploymentMode";
import { apiFetch } from "../../lib/api";
import { TextArea, TextInput } from "../../ui/Field";
import { Button } from "../../ui/Button";

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
  const base = hasOrgSurface(auth.user)
    ? "/v1/org/tenant-content"
    : "/v1/admin/tenant-content";
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
    <section className="rounded-sheet border border-line bg-card p-roomy">
      <h2 className="text-sm font-medium text-ink-primary">{t("org:knowledgePublishTitle")}</h2>
      <p className="mt-base text-xs text-ink-muted">{t("org:cmsSetupHint")}</p>

      <div className="mt-wide">
        <label className="block text-xs text-ink-muted" htmlFor="org-knowledge-title">
          {t("org:knowledgeTitleLabel")}
        </label>
        <TextInput
          id="org-knowledge-title"
          className="mt-tight"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={t("org:knowledgeTitlePlaceholder")}
          autoComplete="off"
        />
      </div>

      <label className="mt-wide block text-xs text-ink-muted" htmlFor="org-knowledge-text">
        {t("org:knowledgeTextLabel")}
      </label>
      <TextArea
        mono
        id="org-knowledge-text"
        className="mt-tight min-h-48"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={t("org:knowledgeTextPlaceholder")}
      />

      <div className="mt-soft flex flex-wrap items-center gap-soft">
        <input
          ref={fileInputRef}
          type="file"
          accept=".md,text/markdown,text/plain"
          className="hidden"
          onChange={(e) => onFileSelected(e.target.files?.[0])}
        />
        <Button
          type="button"
          className="px-soft py-snug text-sm hover:bg-white/5"
          onClick={() => fileInputRef.current?.click()}
        >
          {t("org:knowledgeFileButton")}
        </Button>
        <Button
          variant="primary"
          size="lg"
          type="button"
          disabled={busy}
          className="px-wide py-snug text-sm"
          onClick={() => void publish()}
        >
          {busy ? t("org:knowledgePublishing") : t("org:cmsPublish")}
        </Button>
      </div>

      {msg ? <p className="mt-soft text-sm text-success">{msg}</p> : null}
      {err ? <p className="mt-soft text-sm text-danger">{err}</p> : null}
    </section>
  );
}
