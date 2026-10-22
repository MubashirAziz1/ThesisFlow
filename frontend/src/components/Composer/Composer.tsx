import { useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";

interface ComposerProps {
  disabled: boolean;
  isStreaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

const MAX_TEXTAREA_HEIGHT = 200;

export function Composer({ disabled, isStreaming, onSend, onStop }: ComposerProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const canSend = value.trim().length > 0 && !disabled && !isStreaming;

  const autoResize = () => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
  };

  const submit = () => {
    if (!canSend) return;
    onSend(value);
    setValue("");
    requestAnimationFrame(() => {
      const textarea = textareaRef.current;
      if (textarea) {
        textarea.style.height = "auto";
        textarea.focus();
      }
    });
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <div className="composer__box">
        <label htmlFor="composer-input" className="visually-hidden">
          Message the assistant
        </label>
        <textarea
          id="composer-input"
          ref={textareaRef}
          className="composer__input"
          value={value}
          rows={1}
          placeholder={disabled ? "Backend unavailable…" : "Ask a question…"}
          disabled={disabled}
          onChange={(event) => {
            setValue(event.target.value);
            autoResize();
          }}
          onKeyDown={handleKeyDown}
        />
        {isStreaming ? (
          <button
            type="button"
            className="button button--secondary composer__action"
            onClick={onStop}
            aria-label="Stop generating"
          >
            Stop
          </button>
        ) : (
          <button
            type="submit"
            className="button button--primary composer__action"
            disabled={!canSend}
            aria-label="Send message"
          >
            Send
          </button>
        )}
      </div>
      <p className="composer__hint">Enter to send · Shift + Enter for a new line</p>
    </form>
  );
}
