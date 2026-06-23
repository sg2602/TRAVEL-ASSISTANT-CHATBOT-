import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { authFetch } from "./api";
import Sidebar from "./Sidebar";
import Chat from "./chat";
import Login from "./Login";
import { IconMenu, IconClose } from "./Icons";
import "./index.css";
import Dashboard from "./Dashboard";
export default function App() {
  const { user, loading, logout } = useAuth();
  const [activeChatId, setActiveChatId] = useState(null);
  const [chats, setChats] = useState([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [view, setView] = useState("chat");

  useEffect(() => {
    if (user) {
      fetchChats();
    } else {
      setChats([]);
      setActiveChatId(null);
    }
  }, [user]);

  async function fetchChats() {
    try {
      const res = await authFetch("/chat/list");
      if (res.ok) {
        const data = await res.json();
        setChats(data);
        const savedChatId = localStorage.getItem("travel_active_chat");
        if (savedChatId && data.find((c) => c.chat_id === savedChatId)) {
          setActiveChatId(savedChatId);
        } else {
          localStorage.removeItem("travel_active_chat");
          setActiveChatId(null);
        }
      }
    } catch (e) {
      console.error("Failed to fetch chats", e);
    }
  }

  async function handleNewChat() {
    try {
      const res = await authFetch("/chat/start", {
        method: "POST",
        body: JSON.stringify({ title: "New Chat" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to create chat");
      setChats((prev) => [
        { chat_id: data.chat_id, title: data.title, updated_at: new Date().toISOString() },
        ...prev,
      ]);
      localStorage.setItem("travel_active_chat", data.chat_id);
      setActiveChatId(data.chat_id);
    } catch (e) {
      console.error("Failed to create chat", e);
    }
  }

  async function handleDeleteChat(chatId) {
    try {
      await authFetch(`/chat/${chatId}`, { method: "DELETE" });
      setChats((prev) => prev.filter((c) => c.chat_id !== chatId));
      if (activeChatId === chatId) {
        localStorage.removeItem("travel_active_chat");
        setActiveChatId(null);
      }
    } catch (e) {
      console.error("Failed to delete chat", e);
    }
  }

  async function handleRenameChat(chatId, title) {
    setChats((prev) =>
      prev.map((c) => (c.chat_id === chatId ? { ...c, title } : c))
    );
    try {
      await authFetch(`/chat/${chatId}`, {
        method: "PATCH",
        body: JSON.stringify({ title }),
      });
    } catch (e) {
      console.error("Failed to rename chat", e);
    }
  }

  function handleChatTitleUpdate(chatId, title) {
    console.log("title update", chatId, title, activeChatId);
    setChats((prev) =>
      prev.map((c) => (c.chat_id === chatId ? { ...c, title } : c))
    );
  }

  const activeChat = chats.find((c) => c.chat_id === activeChatId);

  if (loading) {
    return (
      <div className="auth-screen">
        <div className="auth-card auth-card--loading">
          <p>Loading…</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Login />;
  }

  return (
    <div className="app-shell">
      <button
        className="sidebar-toggle"
        onClick={() => setSidebarOpen((o) => !o)}
        aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
      >
        {sidebarOpen ? <IconClose /> : <IconMenu />}
      </button>

      <Sidebar
        open={sidebarOpen}
        chats={chats}
        activeChatId={activeChatId}
        userEmail={user.email}
        onNewChat={handleNewChat}
        onSelectChat={(chatId) => {
          localStorage.setItem("travel_active_chat", chatId);
          setActiveChatId(chatId);
        }}
        onRenameChat={handleRenameChat}
        onDeleteChat={handleDeleteChat}
        onLogout={logout}
        onViewChange={setView}
        currentView={view}
      />

      <main className="main-panel">
        {view === "dashboard" ? (
          <Dashboard onBack={() => setView("chat")} />
        ) : activeChatId ? (
          <Chat
            key={activeChatId}
            chatId={activeChatId}
            chatTitle={activeChat?.title}
            onTitleUpdate={(t) => handleChatTitleUpdate(activeChatId, t)}
          />
        ) : (
          <div className="welcome-screen">
            <div className="welcome-content">
              <h1>Welcome back</h1>
              <p>
                Your conversations are saved to your account and available on
                any device. The assistant adapts to your travel preferences
                over time.
              </p>
              <button className="btn-primary" onClick={handleNewChat}>
                New conversation
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

