/** Extract display content and reasoning from OpenAI-style completion payloads. */

function textFromMessageContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((part: unknown) => {
        if (part && typeof part === "object" && "text" in part) {
          return String((part as { text?: string }).text ?? "");
        }
        return "";
      })
      .join("");
  }
  return "";
}

function reasoningFromMessage(message: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const key of ["reasoning_content", "reasoning", "thinking"] as const) {
    const v = message[key];
    if (typeof v === "string" && v.trim()) parts.push(v.trim());
  }
  return parts.join("\n\n");
}

export function extractAssistantContentFromCompletion(data: unknown): string {
  if (!data || typeof data !== "object") return "";
  const d = data as { choices?: Array<{ message?: Record<string, unknown> }> };
  const msg = d.choices?.[0]?.message;
  if (!msg || typeof msg !== "object") return "";
  return textFromMessageContent(msg.content);
}

export function extractAssistantReasoningFromCompletion(data: unknown): string {
  if (!data || typeof data !== "object") return "";
  const d = data as { choices?: Array<{ message?: Record<string, unknown> }> };
  const msg = d.choices?.[0]?.message;
  if (!msg || typeof msg !== "object") return "";
  return reasoningFromMessage(msg);
}

export function extractSpeechTextFromCompletion(data: unknown): string {
  if (!data || typeof data !== "object") return "";
  const speech = (data as { speech_text?: unknown }).speech_text;
  return typeof speech === "string" ? speech.trim() : "";
}
