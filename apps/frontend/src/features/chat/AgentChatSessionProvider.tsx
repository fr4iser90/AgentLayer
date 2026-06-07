import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useAuth } from "../../auth/AuthContext";
import { getAgentChatSession, type ActiveAgentTurn } from "./agentChatSession";
import type { LiveTurnStore } from "./useAgentLiveTurn";

type AgentChatSessionContextValue = {
  liveTurn: LiveTurnStore;
  getActiveTurn: () => ActiveAgentTurn | null;
  isTurnInProgress: () => boolean;
};

const AgentChatSessionContext = createContext<AgentChatSessionContextValue | null>(null);

export function AgentChatSessionProvider({ children }: { children: ReactNode }) {
  const { accessToken } = useAuth();
  const session = getAgentChatSession();

  useEffect(() => {
    session.setAccessToken(accessToken);
  }, [accessToken, session]);

  const value: AgentChatSessionContextValue = {
    liveTurn: session.liveTurn,
    getActiveTurn: session.getActiveTurn,
    isTurnInProgress: session.isTurnInProgress,
  };

  return (
    <AgentChatSessionContext.Provider value={value}>{children}</AgentChatSessionContext.Provider>
  );
}

export function useAgentChatSession(): AgentChatSessionContextValue {
  const ctx = useContext(AgentChatSessionContext);
  if (!ctx) {
    throw new Error("useAgentChatSession requires AgentChatSessionProvider");
  }
  return ctx;
}
