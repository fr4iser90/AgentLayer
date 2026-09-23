/**
 * Subset JSON-schema form for image generation presets (string, integer, number, enum).
 * File fields (format byte) use file → base64 (raw) for inpaint uploads.
 */

type JsonSchemaProp = {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  enum?: string[];
  minimum?: number;
  maximum?: number;
  format?: string;
  contentEncoding?: string;
};

type Props = {
  properties: Record<string, JsonSchemaProp>;
  required?: string[];
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
};

export function SchemaForm({ properties, required = [], values, onChange }: Props) {
  const keys = Object.keys(properties);

  return (
    <div className="flex flex-col gap-wide">
      {keys.map((key) => {
        const prop = properties[key]!;
        const req = required.includes(key);
        const label = prop.title ?? key;
        const isFile = prop.type === "string" && prop.format === "byte";

        if (isFile) {
          return (
            <label key={key} className="flex flex-col gap-tight">
              <span className="text-sm text-ink-secondary">
                {label}
                {req ? <span className="text-red-400"> *</span> : null}
              </span>
              {prop.description ? (
                <span className="text-xs text-ink-muted">{prop.description}</span>
              ) : null}
              <input
                type="file"
                accept="image/*"
                className="text-sm text-ink-secondary file:mr-base file:rounded-tile file:border-0 file:bg-neutral-700 file:px-base file:py-tight file:text-sm"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (!f) {
                    onChange(key, undefined);
                    return;
                  }
                  const reader = new FileReader();
                  reader.onload = () => {
                    const dataUrl = reader.result as string;
                    const base64 = dataUrl.includes(",") ? dataUrl.split(",")[1]! : dataUrl;
                    onChange(key, base64);
                  };
                  reader.readAsDataURL(f);
                }}
              />
            </label>
          );
        }

        if (prop.enum && prop.enum.length > 0) {
          return (
            <label key={key} className="flex flex-col gap-tight">
              <span className="text-sm text-ink-secondary">{label}</span>
              {prop.description ? (
                <span className="text-xs text-ink-muted">{prop.description}</span>
              ) : null}
              <select
                className="rounded-card border border-line bg-field px-soft py-base text-sm text-ink-primary"
                value={(values[key] as string) ?? ""}
                onChange={(e) => onChange(key, e.target.value === "" ? undefined : e.target.value)}
              >
                {prop.enum.map((opt) => (
                  <option key={opt || "__empty"} value={opt}>
                    {opt === "" ? "(workflow default)" : opt}
                  </option>
                ))}
              </select>
            </label>
          );
        }

        if (prop.type === "integer" || prop.type === "number") {
          const v = values[key];
          const numVal =
            typeof v === "number"
              ? v
              : v === "" || v === undefined
                ? ""
                : Number(v);
          return (
            <label key={key} className="flex flex-col gap-tight">
              <span className="text-sm text-ink-secondary">
                {label}
                {req ? <span className="text-red-400"> *</span> : null}
              </span>
              {prop.description ? (
                <span className="text-xs text-ink-muted">{prop.description}</span>
              ) : null}
              <input
                type="number"
                className="rounded-card border border-line bg-field px-soft py-base text-sm text-ink-primary"
                min={prop.minimum}
                max={prop.maximum}
                value={numVal === "" ? "" : numVal}
                placeholder={prop.default !== undefined ? String(prop.default) : undefined}
                onChange={(e) => {
                  const raw = e.target.value;
                  if (raw === "") {
                    onChange(key, undefined);
                    return;
                  }
                  onChange(key, prop.type === "integer" ? parseInt(raw, 10) : parseFloat(raw));
                }}
              />
            </label>
          );
        }

        const multiline = key === "prompt" || key === "negative_prompt";
        const strVal = values[key] != null ? String(values[key]) : "";

        return (
          <label key={key} className="flex flex-col gap-tight">
            <span className="text-sm text-ink-secondary">
              {label}
              {req ? <span className="text-red-400"> *</span> : null}
            </span>
            {prop.description ? (
              <span className="text-xs text-ink-muted">{prop.description}</span>
            ) : null}
            {multiline ? (
              <textarea
                className="min-h-[88px] rounded-card border border-line bg-field px-soft py-base text-sm text-ink-primary"
                value={strVal}
                placeholder={prop.default !== undefined ? String(prop.default) : undefined}
                onChange={(e) => onChange(key, e.target.value)}
              />
            ) : (
              <input
                type="text"
                className="rounded-card border border-line bg-field px-soft py-base text-sm text-ink-primary"
                value={strVal}
                onChange={(e) => onChange(key, e.target.value)}
              />
            )}
          </label>
        );
      })}
    </div>
  );
}
