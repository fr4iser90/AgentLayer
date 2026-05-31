/** Mirrors useAgentLiveTurn RAF batching (stream + log). */
function createTestStore() {
  let streamText = "";
  let agentLog = [];
  const streamListeners = new Set();
  const logListeners = new Set();
  let streamRaf = null;
  let logRaf = null;
  let streamFlushes = 0;
  let logFlushes = 0;

  const scheduleStreamFlush = () => {
    if (streamRaf != null) return;
    streamRaf = setTimeout(() => {
      streamRaf = null;
      streamFlushes += 1;
      for (const l of streamListeners) l();
    }, 0);
  };

  const scheduleLogFlush = () => {
    if (logRaf != null) return;
    logRaf = setTimeout(() => {
      logRaf = null;
      logFlushes += 1;
      for (const l of logListeners) l();
    }, 0);
  };

  return {
    subscribeStream: (cb) => {
      streamListeners.add(cb);
      return () => streamListeners.delete(cb);
    },
    getStreamText: () => streamText,
    appendStreamDelta: (d) => {
      streamText += d;
      scheduleStreamFlush();
    },
    appendLogLine: () => {
      agentLog = [...agentLog, { id: String(agentLog.length), kind: "llm", text: "x" }];
      scheduleLogFlush();
    },
    get streamFlushes() {
      return streamFlushes;
    },
    get logFlushes() {
      return logFlushes;
    },
  };
}

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exit(1);
  }
}

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

const store = createTestStore();
for (let i = 0; i < 20; i++) store.appendStreamDelta("a");
for (let i = 0; i < 15; i++) store.appendLogLine();
await sleep(5);
assert(store.streamFlushes === 1, "20 stream deltas batched to one flush");
assert(store.logFlushes === 1, "15 log lines batched to one flush");
assert(store.getStreamText().length === 20, "stream text accumulated");

console.log("test-agent-live-turn: ok");
