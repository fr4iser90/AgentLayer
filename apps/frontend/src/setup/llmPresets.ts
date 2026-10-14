/** OpenAI-compatible endpoint presets for setup / admin (base URL + hints). */

export type LlmPresetId =
  | "provider_1"
  | "llama_cpp"
  | "openai"
  | "openrouter"
  | "groq"
  | "together"
  | "custom";

export type ProviderPresetKind = "chat" | "embedding" | "voice_stt" | "voice_tts";

export type LlmPresetConfig = {
  id: LlmPresetId;
  /** i18n key under setup namespace */
  labelKey: string;
  /** Stored as operator_provider_endpoints.label */
  endpointLabel: string;
  baseUrl: string;
  modelPlaceholderKey: string;
  modelExample?: string;
  apiKeyRequired: boolean;
  apiKeyHintKey: string;
  helpKey: string;
};

const KIND_LOCAL_LABEL: Record<ProviderPresetKind, string> = {
  chat: "llmPresetProvider1Label",
  embedding: "embedPresetProvider1Label",
  voice_stt: "voiceSttPresetProvider1Label",
  voice_tts: "voiceTtsPresetProvider1Label",
};

const KIND_LOCAL_HELP: Record<ProviderPresetKind, string> = {
  chat: "llmPresetProvider1Help",
  embedding: "embedPresetProvider1Help",
  voice_stt: "voiceSttPresetProvider1Help",
  voice_tts: "voiceTtsPresetProvider1Help",
};

const KIND_CUSTOM_LABEL: Record<ProviderPresetKind, string> = {
  chat: "LLM",
  embedding: "Embedding",
  voice_stt: "STT",
  voice_tts: "TTS",
};

const KIND_ENDPOINT_LABEL: Record<ProviderPresetKind, string> = {
  chat: "provider_1",
  embedding: "embedding_provider_1",
  voice_stt: "voice_stt_provider_1",
  voice_tts: "voice_tts_provider_1",
};

export const LLM_PRESETS: readonly LlmPresetConfig[] = [
  {
    id: "provider_1",
    labelKey: "llmPresetProvider1Label",
    endpointLabel: "provider_1",
    baseUrl: "",
    modelPlaceholderKey: "llmPresetProvider1ModelPlaceholder",
    apiKeyRequired: false,
    apiKeyHintKey: "llmPresetProvider1ApiKeyHint",
    helpKey: "llmPresetProvider1Help",
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

/** Same preset list for every kind — only local/custom labels follow env prefix. */
export function getPresetForKind(kind: ProviderPresetKind, id: LlmPresetId): LlmPresetConfig {
  const base = getLlmPreset(id);
  if (id === "provider_1") {
    return {
      ...base,
      labelKey: KIND_LOCAL_LABEL[kind],
      helpKey: KIND_LOCAL_HELP[kind],
      endpointLabel: KIND_ENDPOINT_LABEL[kind],
    };
  }
  if (id === "custom") {
    return {
      ...base,
      endpointLabel: KIND_CUSTOM_LABEL[kind],
    };
  }
  return base;
}

export function listPresetsForKind(kind: ProviderPresetKind): LlmPresetConfig[] {
  return LLM_PRESETS.map((p) => getPresetForKind(kind, p.id));
}

export const DEFAULT_LLM_PRESET: LlmPresetId = "provider_1";
