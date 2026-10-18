import { describe, expect, it } from "vitest";
import {
  formatInterruptedBadgeLabel,
  isInterruptTimelineKind,
  threadWithInterruptedTurn,
} from "./interruptedTurn";
import type { ChatThread } from "./chatThreadStorage";

function baseThread(overrides?: Partial<ChatThread>): ChatThread {
  return {
    id: "t1",
    title: "test",
    mode: "agent",
    model: "chat",
    messages: [
      { role: "user", content: "hi", id: "u1", createdAt: 1 },
    ],
    agentLog: [],
    turnLogs: [],
    messageCount: 1,
    updatedAt: 1,
    ...overrides,
  };
}

describe("formatInterruptedBadgeLabel", () => {
  it("formats HTTP 503 thermal", () => {
    expect(
      formatInterruptedBadgeLabel(
        "Language model server returned HTTP 503 (local_temperature_above_limit). Inspect logs."
      )
    ).toBe("Interrupted · 503 · thermal");
  });

  it("formats plain HTTP code", () => {
    expect(
      formatInterruptedBadgeLabel("Language model server returned HTTP 502. Inspect logs.")
    ).toBe("Interrupted · 502");
  });
});

describe("threadWithInterruptedTurn", () => {
  it("keeps empty assistant stub and interrupted marker", () => {
    const th = baseThread({
      agentLog: [
        { id: "1", kind: "tool_done", text: "read file", toolName: "repository.read_file" },
      ],
    });
    const next = threadWithInterruptedTurn(th, {
      streamText: "",
      streamReasoning: "thinking…",
      logBase: th.agentLog ?? [],
      kind: "agent.interrupted",
      markerText: "Interrupted · 503 · thermal",
    });
    expect(next.messages).toHaveLength(2);
    expect(next.messages[1]?.role).toBe("assistant");
    expect(next.messages[1]?.reasoningContent).toBe("thinking…");
    expect(next.agentLog?.some((e) => e.kind === "agent.interrupted")).toBe(true);
    expect(isInterruptTimelineKind("agent.interrupted")).toBe(true);
  });
});
