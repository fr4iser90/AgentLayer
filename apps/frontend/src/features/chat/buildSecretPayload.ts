export type SecretFieldSpec = {
  name: string;
  label?: string;
  type?: string;
  required?: boolean;
};

export type UserSecretFormSpec = {
  title?: string;
  help?: string;
  fields?: SecretFieldSpec[];
};

/** Build POST /v1/user/secrets body from form fields or raw text. */
export function buildUserSecretPostBody(
  serviceKey: string,
  form: UserSecretFormSpec | undefined,
  fieldValues: Record<string, string>,
  rawSecret: string,
  opts?: { scope?: "global" | "workspace"; workspaceId?: string }
): {
  service_key: string;
  secret: string | Record<string, string>;
  scope?: "global" | "workspace";
  workspace_id?: string;
} | null {
  const sk = serviceKey.trim().toLowerCase();
  if (!sk) return null;

  let base: {
    service_key: string;
    secret: string | Record<string, string>;
  } | null = null;

  if (form?.fields?.length) {
    const obj: Record<string, string> = {};
    for (const f of form.fields) {
      let v = (fieldValues[f.name] ?? "").trim();
      if (f.name === "app_password") v = v.replace(/\s+/g, "");
      obj[f.name] = v;
    }
    const missing = form.fields.filter((f) => f.required && !obj[f.name]?.trim());
    if (missing.length) return null;
    base = { service_key: sk, secret: obj };
  } else {
    const raw = rawSecret.trim();
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
        base = { service_key: sk, secret: parsed as Record<string, string> };
      }
    } catch {
      /* plain string */
    }
    if (!base) base = { service_key: sk, secret: raw };
  }

  const scope = opts?.scope === "workspace" ? "workspace" : "global";
  if (scope === "workspace") {
    const wid = opts?.workspaceId?.trim();
    if (!wid) return null;
    return { ...base, scope: "workspace", workspace_id: wid };
  }
  return { ...base, scope: "global" };
}
