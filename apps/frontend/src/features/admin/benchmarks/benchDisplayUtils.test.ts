import { describe, expect, it } from "vitest";
import {
  benchmarkProfileLabel,
  benchmarkProviderName,
  formatBenchmarkProviderModel,
} from "./benchDisplayUtils";

describe("benchDisplayUtils", () => {
  it("strips model suffix from composite profile_label", () => {
    expect(
      benchmarkProviderName({
        profile_label: "OLLAMA · qwen3.5:2b",
        model: "qwen3.5:2b",
      })
    ).toBe("OLLAMA");
  });

  it("formats as Provider / model", () => {
    expect(
      formatBenchmarkProviderModel({
        profile_label: benchmarkProfileLabel("OLLAMA", "qwen3.5:2b"),
        catalog_owned_by: "provider_2",
        model: "qwen3.5:2b",
      })
    ).toBe("OLLAMA / qwen3.5:2b");
  });

  it("falls back to catalog_owned_by when label empty", () => {
    expect(
      formatBenchmarkProviderModel({
        catalog_owned_by: "provider_1",
        model: "qwen.gguf",
      })
    ).toBe("provider_1 / qwen.gguf");
  });
});
