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
  rawSecret: string
): { service_key: string; secret: string | Record<string, string> } | null {
  const sk = serviceKey.trim().toLowerCase();
  if (!sk) return null;

  if (form?.fields?.length) {
    const obj: Record<string, string> = {};
    for (const f of form.fields) {
      let v = (fieldValues[f.name] ?? "").trim();
      if (f.name === "app_password") v = v.replace(/\s+/g, "");
      obj[f.name] = v;
    }
    const missing = form.fields.filter((f) => f.required && !obj[f.name]?.trim());
    if (missing.length) return null;
    return { service_key: sk, secret: obj };
  }

  const raw = rawSecret.trim();
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
      return { service_key: sk, secret: parsed as Record<string, string> };
    }
  } catch {
    /* plain string */
  }
  return { service_key: sk, secret: raw };
}
