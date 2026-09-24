import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AuthContextValue } from "../../auth/AuthContext";
import { patchWorkspace } from "../../lib/api";
import {
  UV_MCP_PRESETS,
  buildUvMcpServerRow,
  defaultServerIdFromPackage,
  mergeMcpServer,
  packageBaseName,
  parseMcpServersJson,
  uvToolInstallCommand,
  type UvMcpLaunchMode,
} from "./workspaceMcpBuilders";
import { Button } from "../../ui/Button";

type Props = {
  open: boolean;
  onClose: () => void;
  auth: Pick<AuthContextValue, "accessToken" | "refresh">;
  workspaceId: string;
  workspaceName: string;
  /** Server-side workspace root (for MCP ``cwd``, e.g. cocoindex indexing). */
  workspacePath?: string | null;
  initialServers: unknown[] | null | undefined;
  onSaved: () => void;
};

const EXAMPLE = `[
  {
    "id": "cocoindex-code",
    "command": "uvx",
    "args": ["--from", "cocoindex-code[full]", "ccc", "mcp"],
    "cwd": "/workspace/…/your-project"
  }
]`;

export function WorkspaceMcpModal({
  open,
  onClose,
  auth,
  workspaceId,
  workspaceName,
  workspacePath,
  initialServers,
  onSaved,
}: Props) {
  const { t } = useTranslation(["workspace"]);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [presetId, setPresetId] = useState("cocoindex-full");
  const [serverId, setServerId] = useState("cocoindex-code");
  const [packageSpec, setPackageSpec] = useState("cocoindex-code[full]");
  const [launchMode, setLaunchMode] = useState<UvMcpLaunchMode>("uvx");
  const [binary, setBinary] = useState("ccc");
  const [mcpArgsText, setMcpArgsText] = useState("mcp");
  const [useWorkspaceCwd, setUseWorkspaceCwd] = useState(true);
  const [uvFormError, setUvFormError] = useState<string | null>(null);

  const preset = useMemo(
    () => UV_MCP_PRESETS.find((p) => p.id === presetId) ?? UV_MCP_PRESETS[0],
    [presetId]
  );

  useEffect(() => {
    if (!open) return;
    setError(null);
    setUvFormError(null);
    const raw = initialServers;
    if (Array.isArray(raw) && raw.length > 0) {
      setText(JSON.stringify(raw, null, 2));
    } else {
      setText("[]");
    }
    const p = UV_MCP_PRESETS.find((x) => x.id === "cocoindex-full") ?? UV_MCP_PRESETS[0];
    setPresetId(p.id);
    setPackageSpec(p.packageSpec);
    setLaunchMode(p.launchMode);
    setBinary(p.binary);
    setMcpArgsText(p.mcpArgs.join(" "));
    setUseWorkspaceCwd(p.useWorkspaceCwd !== false);
    setServerId(defaultServerIdFromPackage(p.packageSpec));
  }, [open, initialServers, workspaceId]);

  const applyPreset = (id: string) => {
    setPresetId(id);
    const p = UV_MCP_PRESETS.find((x) => x.id === id);
    if (!p || id === "custom") return;
    setPackageSpec(p.packageSpec);
    setLaunchMode(p.launchMode);
    setBinary(p.binary);
    setMcpArgsText(p.mcpArgs.join(" "));
    setUseWorkspaceCwd(p.useWorkspaceCwd !== false);
    setServerId(defaultServerIdFromPackage(p.packageSpec));
  };

  const handlePackageSpecChange = (value: string) => {
    setPackageSpec(value);
    setPresetId("custom");
    if (!serverId.trim() || serverId === defaultServerIdFromPackage(packageSpec)) {
      setServerId(defaultServerIdFromPackage(value));
    }
    if (!binary.trim() || binary === packageBaseName(packageSpec)) {
      setBinary(packageBaseName(value));
    }
  };

  const handleAddUvServer = () => {
    setUvFormError(null);
    const mcpArgs = mcpArgsText
      .split(/[\s,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    const built = buildUvMcpServerRow({
      serverId,
      packageSpec,
      launchMode,
      binary,
      mcpArgs,
      workspacePath,
      useWorkspaceCwd,
    });
    if ("error" in built) {
      setUvFormError(built.error);
      return;
    }
    const parsed = parseMcpServersJson(text);
    if ("error" in parsed) {
      setUvFormError(parsed.error);
      return;
    }
    const exists = parsed.servers.some((s) => s.id === built.row.id);
    const next = mergeMcpServer(parsed.servers, built.row, exists);
    setText(JSON.stringify(next, null, 2));
    setUvFormError(null);
  };

  if (!open) return null;

  const handleSave = async () => {
    setError(null);
    const parsed = parseMcpServersJson(text);
    if ("error" in parsed) {
      setError(parsed.error);
      return;
    }
    setSaving(true);
    try {
      const res = await patchWorkspace(auth, workspaceId, { mcp_stdio_servers: parsed.servers });
      if (!res.ok) {
        setError(res.error);
        return;
      }
      onSaved();
      onClose();
    } finally {
      setSaving(false);
    }
  };

  const toolInstallCmd = uvToolInstallCommand(packageSpec);
  const previewBuilt = buildUvMcpServerRow({
    serverId: serverId || "x",
    packageSpec: packageSpec || "pkg",
    launchMode,
    binary,
    mcpArgs: mcpArgsText.split(/[\s,]+/).filter(Boolean),
    workspacePath,
    useWorkspaceCwd,
  });
  const previewRow = "row" in previewBuilt ? previewBuilt.row : null;

  return (
    <div
      className="fixed inset-0 z-modal flex items-center justify-center bg-black/60 p-wide"
      role="dialog"
      aria-modal="true"
    >
      <div className="flex max-h-[92vh] w-full max-w-dialogWide flex-col overflow-hidden rounded-sheet border border-line-strong bg-[#141414] shadow-xl">
        <div className="shrink-0 border-b border-line px-wide py-soft">
          <h2 className="text-sm font-semibold text-ink-primary">{t("workspace:mcpModalTitle")}</h2>
          <p className="mt-tight text-meta leading-snug text-ink-muted">
            {t("workspace:mcpModalDescription", { workspaceName })}
          </p>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-wide py-soft">
          <section className="rounded-card border border-line bg-black/25 p-soft">
            <p className="text-meta font-semibold uppercase tracking-wide text-ink-muted">{t("workspace:addViaUv")}</p>
            <div className="mt-base grid gap-base sm:grid-cols-2">
              <label className="block sm:col-span-2">
                <span className="text-meta text-ink-muted">{t("workspace:presetLabel")}</span>
                <select
                  className="mt-hair w-full rounded-card border border-line bg-field px-base py-snug text-xs text-ink-primary"
                  value={presetId}
                  onChange={(e) => applyPreset(e.target.value)}
                >
                  {UV_MCP_PRESETS.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="text-meta text-ink-muted">{t("workspace:serverIdLabel")}</span>
                <input
                  className="mt-hair w-full rounded-card border border-line bg-field px-base py-snug font-mono text-xs text-ink-primary"
                  value={serverId}
                  onChange={(e) => {
                    setServerId(e.target.value);
                    setPresetId("custom");
                  }}
                  placeholder={t("workspace:serverIdPlaceholder")}
                />
              </label>
              <label className="block">
                <span className="text-meta text-ink-muted">{t("workspace:packageLabel")}</span>
                <input
                  className="mt-hair w-full rounded-card border border-line bg-field px-base py-snug font-mono text-xs text-ink-primary"
                  value={packageSpec}
                  onChange={(e) => handlePackageSpecChange(e.target.value)}
                  placeholder={t("workspace:packagePlaceholder")}
                />
              </label>
              <fieldset className="sm:col-span-2">
                <legend className="text-meta text-ink-muted">{t("workspace:launchOnServer")}</legend>
                <div className="mt-tight flex flex-wrap gap-soft text-xs text-ink-primary">
                  <label className="inline-flex items-center gap-snug">
                    <input
                      type="radio"
                      name="uv-launch"
                      checked={launchMode === "uvx"}
                      onChange={() => setLaunchMode("uvx")}
                    />
                    <span>
                      {t("workspace:launchUvx")}
                    </span>
                  </label>
                  <label className="inline-flex items-center gap-snug">
                    <input
                      type="radio"
                      name="uv-launch"
                      checked={launchMode === "tool"}
                      onChange={() => setLaunchMode("tool")}
                    />
                    <span>
                      {t("workspace:launchTool")}
                    </span>
                  </label>
                </div>
              </fieldset>
              {launchMode === "tool" ? (
                <p className="sm:col-span-2 rounded-tile border border-amber-500/25 bg-amber-950/30 px-base py-snug text-meta leading-snug text-amber-100/90">
                  {t("workspace:onServerOnce")}{" "}
                  <code className="break-all text-amber-200/95">{toolInstallCmd}</code>
                </p>
              ) : null}
              <label className="block">
                <span className="text-meta text-ink-muted">
                  {launchMode === "uvx" ? t("workspace:binaryAfterFromLabel") : t("workspace:binaryOnPathLabel")}
                </span>
                <input
                  className="mt-hair w-full rounded-card border border-line bg-field px-base py-snug font-mono text-xs text-ink-primary"
                  value={binary}
                  onChange={(e) => {
                    setBinary(e.target.value);
                    setPresetId("custom");
                  }}
                  placeholder={t("workspace:binaryPlaceholder")}
                />
              </label>
              <label className="block">
                <span className="text-meta text-ink-muted">{t("workspace:argsLabel")}</span>
                <input
                  className="mt-hair w-full rounded-card border border-line bg-field px-base py-snug font-mono text-xs text-ink-primary"
                  value={mcpArgsText}
                  onChange={(e) => {
                    setMcpArgsText(e.target.value);
                    setPresetId("custom");
                  }}
                  placeholder={t("workspace:argsPlaceholder")}
                />
              </label>
              <label className="flex items-center gap-base sm:col-span-2 text-xs text-ink-secondary">
                <input
                  type="checkbox"
                  checked={useWorkspaceCwd}
                  onChange={(e) => setUseWorkspaceCwd(e.target.checked)}
                />
                {t("workspace:workspaceCwdLabel")} <code className="text-ink-muted">cwd</code>
                {workspacePath ? (
                  <span className="truncate text-meta text-ink-muted" title={workspacePath}>
                    ({workspacePath})
                  </span>
                ) : (
                  <span className="text-meta text-amber-300/90">{t("workspace:workspaceCwdUnknownHint")}</span>
                )}
              </label>
            </div>
            {previewRow ? (
              <pre className="mt-base max-h-20 overflow-auto rounded-tile border border-line-subtle bg-black/40 p-base text-meta text-ink-muted">
                {JSON.stringify(previewRow, null, 2)}
              </pre>
            ) : null}
            {uvFormError ? <p className="mt-base text-xs text-red-300/95">{uvFormError}</p> : null}
            <button
              type="button"
              className="mt-base rounded-card border border-sky-600/50 bg-sky-950/40 px-soft py-snug text-xs font-medium text-sky-200 hover:bg-sky-900/50"
              onClick={handleAddUvServer}
            >
              {t("workspace:addToJsonList")}
            </button>
            {preset.toolInstallHint ? (
              <p className="mt-base text-meta text-ink-muted">
                {t("workspace:optionalPersistentInstallHint", {
                  hint: preset.toolInstallHint,
                  binary: preset.binary,
                })}
              </p>
            ) : null}
          </section>

          <p className="mt-soft text-meta font-semibold uppercase tracking-wide text-ink-muted">{t("workspace:serversJsonTitle")}</p>
          <textarea
            className="mt-tight h-48 w-full resize-y rounded-card border border-line bg-field px-soft py-base font-mono text-xs text-ink-primary"
            spellCheck={false}
            value={text}
            onChange={(e) => setText(e.target.value)}
            aria-label={t("workspace:serversJsonAria")}
          />
          <p className="mt-base text-meta leading-snug text-ink-muted">
            {t("workspace:schemaHint")}{" "}
            <code className="text-ink-muted">id</code>, <code className="text-ink-muted">command</code>,{" "}
            <code className="text-ink-muted">args</code>, optional <code className="text-ink-muted">env</code>,{" "}
            <code className="text-ink-muted">cwd</code>. {t("workspace:cwdHint")}
          </p>
          <pre className="mt-tight max-h-24 overflow-auto rounded-tile border border-line-subtle bg-black/30 p-base text-meta text-ink-muted">
            {EXAMPLE}
          </pre>
        </div>

        {error ? <p className="shrink-0 px-wide pb-base text-xs text-red-300/95">{error}</p> : null}
        <div className="flex shrink-0 justify-end gap-base border-t border-line px-wide py-soft">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={onClose}
            disabled={saving}
          >
            {t("workspace:cancel")}
          </Button>
          <button
            type="button"
            className="rounded-card bg-sky-600 px-soft py-snug text-xs font-medium text-ink-on-fill hover:bg-sky-500 disabled:opacity-50"
            onClick={() => void handleSave()}
            disabled={saving}
          >
            {saving ? t("workspace:saving") : t("workspace:save")}
          </button>
        </div>
      </div>
    </div>
  );
}
