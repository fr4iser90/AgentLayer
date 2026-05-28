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
  /** i18n key under setup namespace */
  labelKey: string;
  /** Stored as operator_external_llm_endpoints.label */
  endpointLabel: string;
  baseUrl: string;
  modelPlaceholderKey: string;
  modelExample?: string;
  apiKeyRequired: boolean;
  apiKeyHintKey: string;
  helpKey: string;
};

export const LLM_PRESETS: readonly LlmPresetConfig[] = [
  {
    id: "ollama",
    labelKey: "llmPresetOllamaLabel",
    endpointLabel: "Ollama",
    baseUrl: "http://ollama:11434",
    modelPlaceholderKey: "llmPresetOllamaModelPlaceholder",
    apiKeyRequired: false,
    apiKeyHintKey: "llmPresetOllamaApiKeyHint",
    helpKey: "llmPresetOllamaHelp",
  },
  {
    id: "llama_cpp",
    labelKey: "llmPresetLlamaCppLabel",
    endpointLabel: "llama.cpp",
    baseUrl: "http://127.0.0.1:8080/v1",
    modelPlaceholderKey: "llmPresetLlamaCppModelPlaceholder",
    apiKeyRequired: false,
    apiKeyHintKey: "llmPresetLlamaCppApiKeyHint",
    helpKey: "llmPresetLlamaCppHelp",
  },
  {
    id: "openai",
    labelKey: "llmPresetOpenaiLabel",
    endpointLabel: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    modelPlaceholderKey: "llmPresetOpenaiModelPlaceholder",
    modelExample: "gpt-4o",
    apiKeyRequired: true,
    apiKeyHintKey: "llmPresetOpenaiApiKeyHint",
    helpKey: "llmPresetOpenaiHelp",
  },
  {
    id: "openrouter",
    labelKey: "llmPresetOpenrouterLabel",
    endpointLabel: "OpenRouter",
    baseUrl: "https://openrouter.ai/api/v1",
    modelPlaceholderKey: "llmPresetOpenrouterModelPlaceholder",
    modelExample: "anthropic/claude-sonnet-4",
    apiKeyRequired: true,
    apiKeyHintKey: "llmPresetOpenrouterApiKeyHint",
    helpKey: "llmPresetOpenrouterHelp",
  },
  {
    id: "groq",
    labelKey: "llmPresetGroqLabel",
    endpointLabel: "Groq",
    baseUrl: "https://api.groq.com/openai/v1",
    modelPlaceholderKey: "llmPresetGroqModelPlaceholder",
    modelExample: "nemotron-3-nano:4b",
    apiKeyRequired: true,
    apiKeyHintKey: "llmPresetGroqApiKeyHint",
    helpKey: "llmPresetGroqHelp",
  },
  {
    id: "together",
    labelKey: "llmPresetTogetherLabel",
    endpointLabel: "Together",
    baseUrl: "https://api.together.xyz/v1",
    modelPlaceholderKey: "llmPresetTogetherModelPlaceholder",
    apiKeyRequired: true,
    apiKeyHintKey: "llmPresetTogetherApiKeyHint",
    helpKey: "llmPresetTogetherHelp",
  },
  {
    id: "custom",
    labelKey: "llmPresetCustomLabel",
    endpointLabel: "LLM",
    baseUrl: "",
    modelPlaceholderKey: "llmPresetCustomModelPlaceholder",
    apiKeyRequired: false,
    apiKeyHintKey: "llmPresetCustomApiKeyHint",
    helpKey: "llmPresetCustomHelp",
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
