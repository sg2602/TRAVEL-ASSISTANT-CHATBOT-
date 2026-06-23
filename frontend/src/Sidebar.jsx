import { useState, useEffect, useRef } from "react";
import { authFetch } from "./api";
import MemoryBadge from "./MemoryBadge";
import { IconPlus, IconEdit, IconTrash, IconChevron } from "./Icons";

function ChatItem({
  chat,
  isActive,
  onSelect,
  onRename,
  onDelete,
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(chat.title);
  const inputRef = useRef(null);

  useEffect(() => {
    setDraft(chat.title);
  }, [chat.title]);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  function startRename(e) {
    e.stopPropagation();
    setEditing(true);
  }

  function commitRename() {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== chat.title) {
      onRename(chat.chat_id, trimmed);
    } else {
      setDraft(chat.title);
    }
    setEditing(false);
  }

  function handleKeyDown(e) {
    if (e.key === "Enter") {
      e.preventDefault();
      commitRename();
    } else if (e.key === "Escape") {
      setDraft(chat.title);
      setEditing(false);
    }
  }

  function formatDate(iso) {
    const d = new Date(iso);
    const now = new Date();
    const diff = (now - d) / 1000;
    if (diff < 60) return "Just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  return (
    <div
      className={`chat-item ${isActive ? "chat-item--active" : ""}`}
      onClick={() => !editing && onSelect(chat.chat_id)}
      onDoubleClick={startRename}
    >
      <div className="chat-item-body">
        {editing ? (
          <input
            ref={inputRef}
            className="chat-item-rename-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commitRename}
            onKeyDown={handleKeyDown}
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <>
            <span className="chat-item-title">{chat.title}</span>
            <span className="chat-item-date">{formatDate(chat.updated_at)}</span>
          </>
        )}
      </div>

      {!editing && (
        <div className="chat-item-actions">
          <button
            className="chat-item-action"
            title="Rename"
            onClick={startRename}
          >
            <IconEdit />
          </button>
          <button
            className="chat-item-action chat-item-action--danger"
            title="Delete"
            onClick={(e) => {
              e.stopPropagation();
              if (window.confirm(`Delete "${chat.title}"?`)) {
                onDelete(chat.chat_id);
              }
            }}
          >
            <IconTrash />
          </button>
        </div>
      )}
    </div>
  );
}

export default function Sidebar({
  open,
  chats,
  activeChatId,
  userEmail,
  onNewChat,
  onSelectChat,
  onRenameChat,
  onDeleteChat,
  onLogout,
  onViewChange,
  currentView
}) {
  const [preferences, setPreferences] = useState({});
  const [showPrefs, setShowPrefs] = useState(false);

  useEffect(() => {
    fetchPreferences();
  }, []);

  async function fetchPreferences() {
    try {
      const res = await authFetch("/chat/preferences");
      if (res.ok) {
        setPreferences(await res.json());
      }
    } catch (e) {
      console.error("Failed to fetch preferences", e);
    }
  }

  return (
    <aside className={`sidebar ${open ? "sidebar--open" : "sidebar--closed"}`}>
      <div className="sidebar-header">
        <span className="sidebar-logo">Travel Assistant</span>
        <button className="btn-new-chat" onClick={onNewChat} title="New chat">
          <IconPlus />
        </button>
      </div>

      <div className="sidebar-section-label">Chats</div>

      <nav className="chat-list">
        {chats.length === 0 ? (
          <p className="chat-list-empty">
            No conversations yet.
            <br />
            Start one to begin planning.
          </p>
        ) : (
          chats.map((chat) => (
            <ChatItem
              key={chat.chat_id}
              chat={chat}
              isActive={activeChatId === chat.chat_id}
              onSelect={onSelectChat}
              onRename={onRenameChat}
              onDelete={onDeleteChat}
            />
          ))
        )}
      </nav>

      <div className="sidebar-divider" />

      <div className="sidebar-memory-section">
        <button
          className="memory-toggle-btn"
          onClick={() => {
            setShowPrefs((s) => !s);
            fetchPreferences();
          }}
        >
          <MemoryBadge count={Object.keys(preferences).length} />
          <span>Your preferences</span>
          <IconChevron open={showPrefs} />
        </button>

        {showPrefs && (
          <div className="preferences-panel">
            <p className="prefs-label">Learned from your chats</p>
            {Object.keys(preferences).length === 0 ? (
              <p className="prefs-empty">
                Preferences appear here as you chat — budget, interests, travel style, and more.
              </p>
            ) : (
              <ul className="prefs-list">
                {Object.entries(preferences).map(([k, v]) => (
                  <li key={k}>
                    <span className="pref-key">{k.replace(/_/g, " ")}</span>
                    {": "}
                    <span className="pref-val">{v}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      <div className="sidebar-footer">
        <span className="user-email">{userEmail}</span>
        <button className="btn-logout" onClick={onLogout}>
          Log out
        </button>
        <button
          className={`analytics-btn ${currentView === "dashboard" ? "analytics-btn--active" : ""}`}
          onClick={() => onViewChange(currentView === "dashboard" ? "chat" : "dashboard")}
        >
          📊 Analytics
        </button>
      </div>
    </aside>
  );
}
