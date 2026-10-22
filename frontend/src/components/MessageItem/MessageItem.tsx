import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../../types";

interface MessageItemProps {
  message: ChatMessage;
}

export function MessageItem({ message }: MessageItemProps) {
  const isUser = message.role === "user";

  return (
    <article
      className={`message message--${message.role}${
        message.status === "error" ? " message--error" : ""
      }`}
    >
      <header className="message__role">{isUser ? "You" : "Assistant"}</header>

      <div className="message__body">
        {isUser ? (
          <p className="message__text">{message.content}</p>
        ) : (
          <>
            <div className="message__markdown">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  a: ({ node: _node, ...props }) => (
                    <a {...props} target="_blank" rel="noreferrer noopener" />
                  ),
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
            {message.status === "streaming" && (
              <span className="message__caret" aria-label="Assistant is typing" />
            )}
          </>
        )}
      </div>

      {message.status === "error" && (
        <p className="message__error-note" role="alert">
          This response was interrupted or failed.
        </p>
      )}
    </article>
  );
}
