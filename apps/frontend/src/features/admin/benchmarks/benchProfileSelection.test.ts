import { describe, expect, it } from "vitest";
import {
  benchmarkProfileLabel,
  formatBenchmarkProviderModel,
} from "./benchDisplayUtils";
import { buildProfilesFromSelection } from "./benchProfileSelection";
import type { BenchmarkLlmProvider } from "./benchmarksApi";

const ollama: BenchmarkLlmProvider = {
  catalog_owned_by: "provider_2",
  label: "OLLAMA",
  base_url: "http://localhost:11434/v1",
  source: "env",
};

describe("benchDisplayUtils", () => {
  it("formats provider / model without duplicating model from composite label", () => {
    expect(
      formatBenchmarkProviderModel({
        profile_label: benchmarkProfileLabel("OLLAMA", "qwen3.5:2b"),
        catalog_owned_by: "provider_2",
        model: "qwen3.5:2b",
      })
    ).toBe("OLLAMA / qwen3.5:2b");
  });
});

describe("benchProfileSelection", () => {
  it("builds one profile per selected model on the same provider", () => {
    const selected = new Set(["provider_2"]);
    const models = new Map([
      ["provider_2", ["qwen2.5:3b", "llama3.2:3b"]],
    ]);
    const profiles = buildProfilesFromSelection([ollama], selected, models);
    expect(profiles).toHaveLength(2);
    expect(profiles[0].model).toBe("qwen2.5:3b");
    expect(profiles[1].model).toBe("llama3.2:3b");
    expect(profiles[0].label).toBe(benchmarkProfileLabel("OLLAMA", "qwen2.5:3b"));
  });

});
