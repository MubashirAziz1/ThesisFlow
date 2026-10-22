import { useEffect, useRef } from "react";
import type { Thread } from "../../types";
import { MessageItem } from "../MessageItem/MessageItem";

interface ChatPanelProps {
  thread: Thread | null;
  runError: string | null;
  onDismissError: () => void;
}

const NEAR_BOTTOM_PX = 120;

export function ChatPanel({ thread, runError, onDismissError }: ChatPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedToBottomRef = useRef(true);

  const messages = thread?.messages ?? [];
  const lastMessage = messages[messages.length - 1];

  // Follow the stream only while the user stays near the bottom; scrolling up
  // to read earlier content must not fight the incoming tokens.
  useEffect(() => {
    const container = scrollRef.current;
    if (container && pinnedToBottomRef.current) {
      container.scrollTop = container.scrollHeight;
    }
  }, [messages.length, lastMessage?.content]);

  const handleScroll = () => {
    const container = scrollRef.current;
    if (!container) return;
    const distance =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    pinnedToBottomRef.current = distance < NEAR_BOTTOM_PX;
  };

  return (
    <div className="chat-panel">
      {runError && (
        <div className="error-banner" role="alert">
          <span className="error-banner__text">{runError}</span>
          <button
            type="button"
            className="error-banner__dismiss"
            onClick={onDismissError}
            aria-label="Dismiss error"
          >
            ×
          </button>
        </div>
      )}

      <div
        className="chat-panel__scroll"
        ref={scrollRef}
        onScroll={handleScroll}
        role="log"
        aria-live="polite"
        aria-label="Conversation messages"
      >
        {messages.length === 0 ? (
          <div className="welcome">
            <h1 className="welcome__title">ThesisFlow</h1>
            <p className="welcome__subtitle">
              Material-science research assistant. Ask a question to begin.
            </p>
          </div>
        ) : (
          <div className="chat-panel__messages">
            {messages.map((message) => (
              <MessageItem key={message.id} message={message} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
