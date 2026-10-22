import type { Thread } from "../../types";

interface SidebarProps {
  threads: Thread[];
  activeThreadId: string | null;
  open: boolean;
  onNewThread: () => void;
  onSelectThread: (threadId: string) => void;
  onDeleteThread: (threadId: string) => void;
  onClose: () => void;
}

function formatDate(timestamp: number): string {
  return new Date(timestamp).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

export function Sidebar({
  threads,
  activeThreadId,
  open,
  onNewThread,
  onSelectThread,
  onDeleteThread,
  onClose,
}: SidebarProps) {
  const sorted = [...threads].sort((a, b) => b.createdAt - a.createdAt);

  return (
    <>
      {open && (
        <div
          className="sidebar-backdrop"
          aria-hidden="true"
          onClick={onClose}
        />
      )}
      <nav
        className={`sidebar${open ? " sidebar--open" : ""}`}
        aria-label="Conversation history"
      >
        <div className="sidebar__header">
          <button type="button" className="button button--primary sidebar__new" onClick={onNewThread}>
            New chat
          </button>
        </div>

        {sorted.length === 0 ? (
          <p className="sidebar__empty">No conversations yet.</p>
        ) : (
          <ul className="sidebar__list" role="list">
            {sorted.map((thread) => (
              <li key={thread.id}>
                <div
                  className={`sidebar__item${
                    thread.id === activeThreadId ? " sidebar__item--active" : ""
                  }`}
                >
                  <button
                    type="button"
                    className="sidebar__item-button"
                    onClick={() => onSelectThread(thread.id)}
                    aria-current={thread.id === activeThreadId ? "true" : undefined}
                  >
                    <span className="sidebar__item-title">{thread.title}</span>
                    <span className="sidebar__item-date">
                      {formatDate(thread.createdAt)}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="sidebar__item-delete"
                    aria-label={`Delete conversation "${thread.title}"`}
                    title="Delete conversation"
                    onClick={() => onDeleteThread(thread.id)}
                  >
                    ×
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </nav>
    </>
  );
}
