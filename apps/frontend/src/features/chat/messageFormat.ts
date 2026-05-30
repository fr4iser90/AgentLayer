/** OpenAI-style multimodal user messages stored as JSON string in `UiMessage.content`. */

export type PendingAttachment =
  | { kind: "image"; name: string; dataUrl: string }
  | { kind: "textfile"; name: string; text: string }
  | { kind: "unsupported"; name: string; hint: string };

const MAX_IMAGE_BYTES = 4 * 1024 * 1024;
const MAX_TEXT_BYTES = 256 * 1024;

function readFileAsDataURL(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsDataURL(f);
  });
}

function readFileSliceText(f: File, max: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    const slice = f.size > max ? f.slice(0, max) : f;
    r.readAsText(slice);
  });
}

export async function filesToAttachments(files: FileList | File[]): Promise<PendingAttachment[]> {
  const list = Array.from(files);
  const out: PendingAttachment[] = [];
  for (const f of list) {
    if (f.type.startsWith("image/")) {
      if (f.size > MAX_IMAGE_BYTES) {
        out.push({
          kind: "unsupported",
          name: f.name,
          hint: "Image too large (max 4 MB).",
        });
        continue;
      }
      const dataUrl = await readFileAsDataURL(f);
      out.push({ kind: "image", name: f.name, dataUrl });
      continue;
    }
    if (f.type === "application/zip" || f.name.toLowerCase().endsWith(".zip")) {
      out.push({
        kind: "unsupported",
        name: f.name,
        hint: "ZIP is not unpacked in the browser. Use images or text files, or extract locally and paste.",
      });
      continue;
    }
    if (f.type.startsWith("text/") || /\.(txt|md|json|csv|log|yaml|yml)$/i.test(f.name)) {
      const text = await readFileSliceText(f, MAX_TEXT_BYTES);
      out.push({ kind: "textfile", name: f.name, text: text + (f.size > MAX_TEXT_BYTES ? "\n…(truncated)" : "") });
      continue;
    }
    out.push({
      kind: "unsupported",
      name: f.name,
      hint: "Not sent to the model here. Use PNG/JPEG/WebP/GIF/WebP or .txt/.md/.json.",
    });
  }
  return out;
}

/** Stored string for `UiMessage.content` (plain text or JSON array of OpenAI-style parts). */
export function buildUserMessageContent(
  text: string,
  attachments: PendingAttachment[]
): string {
  const lines: string[] = [];
  const t = text.trim();
  if (t) lines.push(t);
  const imageParts: Array<Record<string, unknown>> = [];
  for (const a of attachments) {
    if (a.kind === "image") {
      // Server-only hint so tools (e.g. run_iterative_html_build) can persist uploads/hero.png etc.
      imageParts.push({
        type: "image_url",
        image_url: { url: a.dataUrl },
        agent_filename: a.name,
      });
    } else if (a.kind === "textfile") {
      lines.push(`[File: ${a.name}]\n${a.text}`);
    } else {
      lines.push(`[${a.name}] ${a.hint}`);
    }
  }
  const combinedText = lines.join("\n\n").trim();
  const parts: Array<Record<string, unknown>> = [];
  if (combinedText) {
    parts.push({ type: "text", text: combinedText });
  }
  for (const im of imageParts) {
    parts.push(im);
  }
  if (parts.length === 0) return "";
  if (parts.length === 1 && parts[0].type === "text") {
    return String(parts[0].text ?? "");
  }
  return JSON.stringify(parts);
}

/** API payload: string or structured content for /v1/chat/completions. */
export function toApiContent(stored: string): string | unknown[] {
  const s = stored.trim();
  if (s.startsWith("[")) {
    try {
      const p = JSON.parse(stored) as unknown;
      if (Array.isArray(p)) return p;
    } catch {
      /* plain text that happens to start with [ */
    }
  }
  return stored;
}

export function normalizeServerContent(c: unknown): string {
  if (typeof c === "string") return c;
  if (Array.isArray(c) || (typeof c === "object" && c !== null)) {
    return JSON.stringify(c);
  }
  return String(c ?? "");
}

type Part = {
  type?: string;
  text?: string;
  image_url?: { url?: string };
  agent_filename?: string;
};

export function parseContentParts(content: string): { plain: string; parts: Part[] | null } {
  const s = content.trim();
  if (!s.startsWith("[")) return { plain: content, parts: null };
  try {
    const p = JSON.parse(s) as unknown;
    if (!Array.isArray(p)) return { plain: content, parts: null };
    const parts = p as Part[];
    if (!parts.some((x) => x.type === "image_url" || x.type === "text")) {
      return { plain: content, parts: null };
    }
    return { plain: "", parts };
  } catch {
    return { plain: content, parts: null };
  }
}

/** Plain user text for clipboard (excludes embedded file bodies and images). */
export function userMessagePlainText(content: string): string {
  const { plain, parts } = parseContentParts(content);
  if (parts) {
    return parts
      .filter((p) => p.type === "text" && p.text)
      .map((p) => String(p.text ?? ""))
      .join("\n\n")
      .trim();
  }
  return stripEmbeddedFileBlocks(plain).trim();
}

const EMBEDDED_FILE_RE =
  /(?:^|\n\n)\[File: ([^\]]+)\]\n[\s\S]*?(?=\n\n\[File: |\n\n\[[^\]]+\] |$)/g;

function stripEmbeddedFileBlocks(text: string): string {
  return text.replace(EMBEDDED_FILE_RE, "").trim();
}

/** Best-effort reverse of ``buildUserMessageContent`` for composer restore / retry. */
export function userMessageToComposerState(content: string): {
  draft: string;
  attachments: PendingAttachment[];
} {
  const attachments: PendingAttachment[] = [];
  const { plain, parts } = parseContentParts(content);
  if (parts) {
    const textLines: string[] = [];
    for (const p of parts) {
      if (p.type === "text" && p.text) {
        textLines.push(String(p.text));
      } else if (p.type === "image_url" && p.image_url?.url) {
        attachments.push({
          kind: "image",
          name: typeof p.agent_filename === "string" && p.agent_filename.trim()
            ? p.agent_filename.trim()
            : "image",
          dataUrl: p.image_url.url,
        });
      }
    }
    return { draft: textLines.join("\n\n"), attachments };
  }

  let draft = plain;
  const fileRe = /(?:^|\n\n)\[File: ([^\]]+)\]\n([\s\S]*?)(?=\n\n\[File: |\n\n\[[^\]]+\] |$)/g;
  let m: RegExpExecArray | null;
  while ((m = fileRe.exec(plain)) !== null) {
    attachments.push({
      kind: "textfile",
      name: m[1] ?? "file",
      text: (m[2] ?? "").trimEnd(),
    });
  }
  draft = stripEmbeddedFileBlocks(plain);
  return { draft, attachments };
}
