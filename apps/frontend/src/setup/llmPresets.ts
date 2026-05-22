/** OpenAI-compatible LLM endpoint presets for setup / admin (base URL + hints). */

export type LlmPresetId =
  | "ollama"
  | "llama_cpp"
  | "openai"
  | "openrouter"
  | "groq"
  | "together"
  | "custom";

export type LlmPresetConfig = {
  id: LlmPresetId;
  /** Short label in the preset dropdown */
  label: string;
  /** Stored as operator_external_llm_endpoints.label */
  endpointLabel: string;
  baseUrl: string;
  modelPlaceholder: string;
  modelExample?: string;
  apiKeyRequired: boolean;
  apiKeyHint: string;
  help: string;
};

export const LLM_PRESETS: readonly LlmPresetConfig[] = [
  {
    id: "ollama",
    label: "Ollama (lokal / Docker)",
    endpointLabel: "Ollama",
    baseUrl: "http://ollama:11434",
    modelPlaceholder: "z. B. qwen2.5:7b",
    apiKeyRequired: false,
    apiKeyHint: "Meist leer (lokaler Server ohne Auth).",
    help: "OpenAI-kompatibel unter /v1. In Docker typisch http://ollama:11434.",
  },
  {
    id: "llama_cpp",
    label: "llama.cpp Server",
    endpointLabel: "llama.cpp",
    baseUrl: "http://127.0.0.1:8080/v1",
    modelPlaceholder: "z. B. Qwen3-8B-Q4_K_M.gguf",
    apiKeyRequired: false,
    apiKeyHint: "Nur wenn Ihr Gateway einen API-Key verlangt.",
    help: "Eigener llama.cpp- oder Gateway-Endpunkt mit /v1/chat/completions.",
  },
  {
    id: "openai",
    label: "OpenAI",
    endpointLabel: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    modelPlaceholder: "z. B. gpt-4o",
    modelExample: "gpt-4o",
    apiKeyRequired: true,
    apiKeyHint: "API-Key von platform.openai.com (sk-…).",
    help: "Offizielle OpenAI-API. Modell-IDs wie gpt-4o, gpt-4o-mini.",
  },
  {
    id: "openrouter",
    label: "OpenRouter (Claude, GPT, Gemini, …)",
    endpointLabel: "OpenRouter",
    baseUrl: "https://openrouter.ai/api/v1",
    modelPlaceholder: "z. B. anthropic/claude-sonnet-4",
    modelExample: "anthropic/claude-sonnet-4",
    apiKeyRequired: true,
    apiKeyHint: "API-Key von openrouter.ai — ein Endpoint für viele Anbieter.",
    help: "Claude ohne nativen Anthropic-Adapter: Modell-ID anthropic/claude-… wählen. Liste unter openrouter.ai/models.",
  },
  {
    id: "groq",
    label: "Groq",
    endpointLabel: "Groq",
    baseUrl: "https://api.groq.com/openai/v1",
    modelPlaceholder: "z. B. nemotron-3-nano:4b",
    modelExample: "nemotron-3-nano:4b",
    apiKeyRequired: true,
    apiKeyHint: "API-Key von console.groq.com.",
    help: "Schnelle Inference; OpenAI-kompatibles /v1.",
  },
  {
    id: "together",
    label: "Together AI",
    endpointLabel: "Together",
    baseUrl: "https://api.together.xyz/v1",
    modelPlaceholder: "z. B. meta-llama/Llama-3.3-70B-Instruct-Turbo",
    apiKeyRequired: true,
    apiKeyHint: "API-Key von api.together.xyz.",
    help: "Viele Open-Source- und Hosted-Modelle über eine OpenAI-kompatible API.",
  },
  {
    id: "custom",
    label: "Benutzerdefiniert",
    endpointLabel: "LLM",
    baseUrl: "",
    modelPlaceholder: "Modell-ID vom Anbieter",
    apiKeyRequired: false,
    apiKeyHint: "Bearer-Token, falls der Anbieter Auth verlangt.",
    help: "Beliebiger OpenAI-kompatibler Endpunkt (LiteLLM, eigener Proxy, …).",
  },
] as const;

const PRESET_BY_ID = Object.fromEntries(LLM_PRESETS.map((p) => [p.id, p])) as Record<
  LlmPresetId,
  LlmPresetConfig
>;

export function getLlmPreset(id: LlmPresetId): LlmPresetConfig {
  return PRESET_BY_ID[id] ?? PRESET_BY_ID.custom;
}

export const DEFAULT_LLM_PRESET: LlmPresetId = "ollama";
