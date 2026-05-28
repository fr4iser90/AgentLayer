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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-white/15 bg-[#141414] shadow-xl">
        <div className="shrink-0 border-b border-white/10 px-4 py-3">
          <h2 className="text-sm font-semibold text-white">{t("workspace:mcpModalTitle")}</h2>
          <p className="mt-1 text-[11px] leading-snug text-surface-muted">
            {t("workspace:mcpModalDescription", { workspaceName })}
          </p>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          <section className="rounded-lg border border-white/10 bg-black/25 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-surface-muted">{t("workspace:addViaUv")}</p>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <label className="block sm:col-span-2">
                <span className="text-[10px] text-surface-muted">{t("workspace:presetLabel")}</span>
                <select
                  className="mt-0.5 w-full rounded-lg border border-surface-border bg-[#1a1a1a] px-2 py-1.5 text-xs text-neutral-100"
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
                <span className="text-[10px] text-surface-muted">{t("workspace:serverIdLabel")}</span>
                <input
                  className="mt-0.5 w-full rounded-lg border border-surface-border bg-black/40 px-2 py-1.5 font-mono text-xs text-neutral-100"
                  value={serverId}
                  onChange={(e) => {
                    setServerId(e.target.value);
                    setPresetId("custom");
                  }}
                  placeholder={t("workspace:serverIdPlaceholder")}
                />
              </label>
              <label className="block">
                <span className="text-[10px] text-surface-muted">{t("workspace:packageLabel")}</span>
                <input
                  className="mt-0.5 w-full rounded-lg border border-surface-border bg-black/40 px-2 py-1.5 font-mono text-xs text-neutral-100"
                  value={packageSpec}
                  onChange={(e) => handlePackageSpecChange(e.target.value)}
                  placeholder={t("workspace:packagePlaceholder")}
                />
              </label>
              <fieldset className="sm:col-span-2">
                <legend className="text-[10px] text-surface-muted">{t("workspace:launchOnServer")}</legend>
                <div className="mt-1 flex flex-wrap gap-3 text-xs text-neutral-200">
                  <label className="inline-flex items-center gap-1.5">
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
                  <label className="inline-flex items-center gap-1.5">
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
                <p className="sm:col-span-2 rounded border border-amber-500/25 bg-amber-950/30 px-2 py-1.5 text-[10px] leading-snug text-amber-100/90">
                  {t("workspace:onServerOnce")}{" "}
                  <code className="break-all text-amber-200/95">{toolInstallCmd}</code>
                </p>
              ) : null}
              <label className="block">
                <span className="text-[10px] text-surface-muted">
                  {launchMode === "uvx" ? t("workspace:binaryAfterFromLabel") : t("workspace:binaryOnPathLabel")}
                </span>
                <input
                  className="mt-0.5 w-full rounded-lg border border-surface-border bg-black/40 px-2 py-1.5 font-mono text-xs text-neutral-100"
                  value={binary}
                  onChange={(e) => {
                    setBinary(e.target.value);
                    setPresetId("custom");
                  }}
                  placeholder={t("workspace:binaryPlaceholder")}
                />
              </label>
              <label className="block">
                <span className="text-[10px] text-surface-muted">{t("workspace:argsLabel")}</span>
                <input
                  className="mt-0.5 w-full rounded-lg border border-surface-border bg-black/40 px-2 py-1.5 font-mono text-xs text-neutral-100"
                  value={mcpArgsText}
                  onChange={(e) => {
                    setMcpArgsText(e.target.value);
                    setPresetId("custom");
                  }}
                  placeholder={t("workspace:argsPlaceholder")}
                />
              </label>
              <label className="flex items-center gap-2 sm:col-span-2 text-xs text-neutral-300">
                <input
                  type="checkbox"
                  checked={useWorkspaceCwd}
                  onChange={(e) => setUseWorkspaceCwd(e.target.checked)}
                />
                {t("workspace:workspaceCwdLabel")} <code className="text-neutral-400">cwd</code>
                {workspacePath ? (
                  <span className="truncate text-[10px] text-surface-muted" title={workspacePath}>
                    ({workspacePath})
                  </span>
                ) : (
                  <span className="text-[10px] text-amber-300/90">{t("workspace:workspaceCwdUnknownHint")}</span>
                )}
              </label>
            </div>
            {previewRow ? (
              <pre className="mt-2 max-h-20 overflow-auto rounded border border-white/5 bg-black/40 p-2 text-[10px] text-neutral-400">
                {JSON.stringify(previewRow, null, 2)}
              </pre>
            ) : null}
            {uvFormError ? <p className="mt-2 text-xs text-red-300/95">{uvFormError}</p> : null}
            <button
              type="button"
              className="mt-2 rounded-lg border border-sky-600/50 bg-sky-950/40 px-3 py-1.5 text-xs font-medium text-sky-200 hover:bg-sky-900/50"
              onClick={handleAddUvServer}
            >
              {t("workspace:addToJsonList")}
            </button>
            {preset.toolInstallHint ? (
              <p className="mt-2 text-[10px] text-surface-muted">
                {t("workspace:optionalPersistentInstallHint", {
                  hint: preset.toolInstallHint,
                  binary: preset.binary,
                })}
              </p>
            ) : null}
          </section>

          <p className="mt-3 text-[10px] font-semibold uppercase tracking-wide text-surface-muted">{t("workspace:serversJsonTitle")}</p>
          <textarea
            className="mt-1 h-48 w-full resize-y rounded-lg border border-surface-border bg-black/40 px-3 py-2 font-mono text-xs text-neutral-100"
            spellCheck={false}
            value={text}
            onChange={(e) => setText(e.target.value)}
            aria-label={t("workspace:serversJsonAria")}
          />
          <p className="mt-2 text-[10px] leading-snug text-surface-muted">
            {t("workspace:schemaHint")}{" "}
            <code className="text-neutral-500">id</code>, <code className="text-neutral-500">command</code>,{" "}
            <code className="text-neutral-500">args</code>, optional <code className="text-neutral-500">env</code>,{" "}
            <code className="text-neutral-500">cwd</code>. {t("workspace:cwdHint")}
          </p>
          <pre className="mt-1 max-h-24 overflow-auto rounded border border-white/5 bg-black/30 p-2 text-[10px] text-neutral-400">
            {EXAMPLE}
          </pre>
        </div>

        {error ? <p className="shrink-0 px-4 pb-2 text-xs text-red-300/95">{error}</p> : null}
        <div className="flex shrink-0 justify-end gap-2 border-t border-white/10 px-4 py-3">
          <button
            type="button"
            className="rounded-lg border border-white/15 px-3 py-1.5 text-xs text-neutral-200 hover:bg-white/5"
            onClick={onClose}
            disabled={saving}
          >
            {t("workspace:cancel")}
          </button>
          <button
            type="button"
            className="rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
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
