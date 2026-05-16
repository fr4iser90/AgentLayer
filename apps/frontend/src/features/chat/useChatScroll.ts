import { useCallback, useEffect, useRef, useState } from "react";

const NEAR_BOTTOM_PX = 120;

export function useChatScroll(deps: {
  messageCount: number;
  loading: boolean;
  activeThreadId: string | null;
  /** Bump when async thread detail has loaded (messages populated). */
  threadContentKey?: string;
}) {
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const isNearBottomRef = useRef(true);
  const [showScrollFab, setShowScrollFab] = useState(false);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    const el = scrollContainerRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior });
    } else {
      messagesEndRef.current?.scrollIntoView({ behavior, block: "end" });
    }
    isNearBottomRef.current = true;
    setShowScrollFab(false);
  }, []);

  const onScrollContainerScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const near =
      el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
    isNearBottomRef.current = near;
    setShowScrollFab(!near);
  }, []);

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    el.addEventListener("scroll", onScrollContainerScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScrollContainerScroll);
  }, [onScrollContainerScroll, deps.activeThreadId]);

  useEffect(() => {
    isNearBottomRef.current = true;
    setShowScrollFab(false);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => scrollToBottom("instant"));
    });
  }, [deps.activeThreadId, deps.threadContentKey, scrollToBottom]);

  useEffect(() => {
    if (isNearBottomRef.current) {
      scrollToBottom(deps.loading ? "smooth" : "smooth");
    }
  }, [deps.messageCount, deps.loading, scrollToBottom]);

  return {
    scrollContainerRef,
    messagesEndRef,
    scrollToBottom,
    showScrollFab,
    isNearBottomRef,
  };
}
