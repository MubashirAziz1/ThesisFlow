import { useCallback, useEffect, useRef, useState } from "react";
import { streamRun } from "../api/client";
import type { ChatMessage, Thread } from "../types";

const STORAGE_KEY = "thesisflow.chat.v1";
const MAX_TITLE_LENGTH = 48;

function loadThreads(): Thread[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Thread[];
    if (!Array.isArray(parsed)) return [];
    // Never resurrect a half-streamed message from a previous session.
    return parsed.map((thread) => ({
      ...thread,
      messages: thread.messages.map((message) =>
        message.status === "streaming"
          ? { ...message, status: "error" as const }
          : message,
      ),
    }));
  } catch {
    return [];
  }
}

function titleFrom(text: string): string {
  const singleLine = text.replace(/\s+/g, " ").trim();
  return singleLine.length > MAX_TITLE_LENGTH
    ? `${singleLine.slice(0, MAX_TITLE_LENGTH - 1)}…`
    : singleLine;
}

export interface UseChatResult {
  threads: Thread[];
  activeThread: Thread | null;
  activeThreadId: string | null;
  isStreaming: boolean;
  runError: string | null;
  sendMessage: (text: string) => Promise<void>;
  stopStreaming: () => void;
  newThread: () => void;
  selectThread: (threadId: string) => void;
  deleteThread: (threadId: string) => void;
  clearError: () => void;
}

/**
 * Chat state: thread list (persisted to localStorage), the active thread, and
 * the lifecycle of one streamed run at a time.
 *
 * The backend keeps no conversational state between runs (the agent graph is
 * compiled without a checkpointer), so only the latest user message is sent
 * with each run.
 */
export function useChat(): UseChatResult {
  const [threads, setThreads] = useState<Thread[]>(loadThreads);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(
    () => loadThreads()[0]?.id ?? null,
  );
  const [isStreaming, setIsStreaming] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const threadsRef = useRef(threads);
  threadsRef.current = threads;

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(threads));
    } catch {
      // Storage full or unavailable — chat still works for this session.
    }
  }, [threads]);

  // Abort an in-flight run if the component unmounts.
  useEffect(() => () => abortRef.current?.abort(), []);

  const patchMessage = useCallback(
    (
      threadId: string,
      messageId: string,
      patch: (message: ChatMessage) => ChatMessage,
    ) => {
      setThreads((previous) =>
        previous.map((thread) =>
          thread.id !== threadId
            ? thread
            : {
                ...thread,
                messages: thread.messages.map((message) =>
                  message.id === messageId ? patch(message) : message,
                ),
              },
        ),
      );
    },
    [],
  );

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || abortRef.current) return;

      setRunError(null);

      // Resolve the target thread, creating one lazily on the first message.
      let threadId = activeThreadId;
      const existing = threadsRef.current.find((t) => t.id === threadId);
      if (!existing) {
        threadId = crypto.randomUUID();
        const thread: Thread = {
          id: threadId,
          title: titleFrom(trimmed),
          createdAt: Date.now(),
          messages: [],
        };
        threadsRef.current = [thread, ...threadsRef.current];
        setThreads(threadsRef.current);
        setActiveThreadId(threadId);
      } else if (existing.messages.length === 0) {
        // First message in a freshly created thread sets its title.
        patchMessageTitle(threadId!, trimmed);
      }

      if (!threadId) return; // Unreachable — resolution above guarantees it.
      const targetThreadId = threadId;

      const userMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: trimmed,
        status: "done",
        createdAt: Date.now(),
      };
      const assistantMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "",
        status: "streaming",
        createdAt: Date.now(),
      };

      setThreads((previous) =>
        previous.map((thread) =>
          thread.id === targetThreadId
            ? {
                ...thread,
                messages: [...thread.messages, userMessage, assistantMessage],
              }
            : thread,
        ),
      );

      const controller = new AbortController();
      abortRef.current = controller;
      setIsStreaming(true);

      let failed = false;
      try {
        await streamRun(targetThreadId, [{ role: "user", content: trimmed }], controller.signal, {
          onMessageChunk: (delta) =>
            patchMessage(targetThreadId, assistantMessage.id, (message) => ({
              ...message,
              content: message.content + delta,
            })),
          onErrorEvent: (error) => {
            failed = true;
            setRunError(error.message);
            patchMessage(targetThreadId, assistantMessage.id, (message) => ({
              ...message,
              status: "error",
            }));
          },
        });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          // User pressed Stop: keep the partial answer.
        } else {
          failed = true;
          setRunError(
            error instanceof Error ? error.message : "Unexpected streaming error",
          );
        }
      } finally {
        patchMessage(targetThreadId, assistantMessage.id, (message) => ({
          ...message,
          status: failed ? "error" : "done",
        }));
        abortRef.current = null;
        setIsStreaming(false);
      }
    },
    [activeThreadId, patchMessage],
  );

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const newThread = useCallback(() => {
    setActiveThreadId(null);
    setRunError(null);
  }, []);

  const selectThread = useCallback((threadId: string) => {
    setActiveThreadId(threadId);
    setRunError(null);
  }, []);

  const deleteThread = useCallback(
    (threadId: string) => {
      setThreads((previous) => previous.filter((t) => t.id !== threadId));
      if (activeThreadId === threadId) setActiveThreadId(null);
    },
    [activeThreadId],
  );

  const clearError = useCallback(() => setRunError(null), []);

  function patchMessageTitle(threadId: string, text: string) {
    setThreads((previous) =>
      previous.map((thread) =>
        thread.id === threadId ? { ...thread, title: titleFrom(text) } : thread,
      ),
    );
  }

  const activeThread =
    threads.find((thread) => thread.id === activeThreadId) ?? null;

  return {
    threads,
    activeThread,
    activeThreadId,
    isStreaming,
    runError,
    sendMessage,
    stopStreaming,
    newThread,
    selectThread,
    deleteThread,
    clearError,
  };
}
