import { useCallback, useEffect, useState } from "react";
import { checkHealth } from "./api/client";
import { ChatPanel } from "./components/ChatPanel/ChatPanel";
import { Composer } from "./components/Composer/Composer";
import { Sidebar } from "./components/Sidebar/Sidebar";
import { useChat } from "./hooks/useChat";
import type { BackendStatus } from "./types";

const OFFLINE_POLL_MS = 15_000;

export default function App() {
  const {
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
  } = useChat();

  const [backendStatus, setBackendStatus] = useState<BackendStatus>("checking");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const refreshHealth = useCallback(async () => {
    const online = await checkHealth();
    setBackendStatus(online ? "online" : "offline");
  }, []);

  useEffect(() => {
    void refreshHealth();
  }, [refreshHealth]);

  // While offline, poll quietly so the UI recovers when the backend starts.
  useEffect(() => {
    if (backendStatus !== "offline") return;
    const timer = setInterval(() => void refreshHealth(), OFFLINE_POLL_MS);
    return () => clearInterval(timer);
  }, [backendStatus, refreshHealth]);

  const handleSelectThread = (threadId: string) => {
    selectThread(threadId);
    setSidebarOpen(false);
  };

  const handleNewThread = () => {
    newThread();
    setSidebarOpen(false);
  };

  const backendOffline = backendStatus === "offline";

  return (
    <div className="app">
      <Sidebar
        threads={threads}
        activeThreadId={activeThreadId}
        open={sidebarOpen}
        onNewThread={handleNewThread}
        onSelectThread={handleSelectThread}
        onDeleteThread={deleteThread}
        onClose={() => setSidebarOpen(false)}
      />

      <main className="main">
        <header className="header">
          <button
            type="button"
            className="header__menu"
            aria-label="Toggle conversation list"
            aria-expanded={sidebarOpen}
            onClick={() => setSidebarOpen((open) => !open)}
          >
            ☰
          </button>
          <span className="header__title">ThesisFlow</span>
          <span className={`status status--${backendStatus}`} role="status">
            <span className="status__dot" aria-hidden="true" />
            <span className="status__label">
              {backendStatus === "checking" && "Connecting…"}
              {backendStatus === "online" && "Connected"}
              {backendStatus === "offline" && "Backend offline"}
            </span>
            {backendOffline && (
              <button
                type="button"
                className="status__retry"
                onClick={() => void refreshHealth()}
              >
                Retry
              </button>
            )}
          </span>
        </header>

        <ChatPanel
          thread={activeThread}
          runError={runError}
          onDismissError={clearError}
        />

        <Composer
          disabled={backendOffline}
          isStreaming={isStreaming}
          onSend={(text) => void sendMessage(text)}
          onStop={stopStreaming}
        />
      </main>
    </div>
  );
}
