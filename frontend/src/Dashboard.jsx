import { useState, useEffect } from "react";
import { authFetch } from "./api";

function StatCard({ label, value, sub }) {
  return (
    <div className="stat-card">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

function MiniBar({ value, max, label }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="mini-bar-row">
      <span className="mini-bar-label">{label}</span>
      <div className="mini-bar-track">
        <div className="mini-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="mini-bar-value">{value.toLocaleString()}</span>
    </div>
  );
}

export default function Dashboard({ onBack }) {
  const [total, setTotal] = useState(null);
  const [daily, setDaily] = useState([]);
  const [byChat, setByChat] = useState([]);
  const [errors, setErrors] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [t, d, c, e] = await Promise.all([
          authFetch("/usage/me/total").then(r => r.json()),
          authFetch("/usage/me/daily").then(r => r.json()),
          authFetch("/usage/me/by-chat").then(r => r.json()),
          authFetch("/debug/errors").then(r => r.json()),
        ]);
        setTotal(t);
        setDaily(d.slice(0, 7).reverse());
        setByChat(c);
        setErrors(e);
      } catch (e) {
        console.error("Failed to load dashboard", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="dashboard-loading">
        <p>Loading analytics…</p>
      </div>
    );
  }

  const maxDailyTokens = Math.max(...daily.map(d => d.total_tokens), 1);
  const maxChatTokens = Math.max(...byChat.map(c => c.total_tokens), 1);

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <button className="btn-back" onClick={onBack}>← Back to Chat</button>
        <h1 className="dashboard-title">📊 Usage Analytics</h1>
        <p className="dashboard-sub">Your personal LLM usage and cost tracking</p>
      </div>

      {/* Stats row */}
      <div className="stat-cards">
        <StatCard
          label="Total API Calls"
          value={total?.total_calls?.toLocaleString() ?? "0"}
        />
        <StatCard
          label="Total Tokens"
          value={total?.total_tokens?.toLocaleString() ?? "0"}
          sub={`${total?.total_input?.toLocaleString()} in / ${total?.total_output?.toLocaleString()} out`}
        />
        <StatCard
          label="Today's Tokens"
          value={daily[daily.length - 1]?.total_tokens?.toLocaleString() ?? "0"}
        />
        <StatCard
          label="Avg Tokens/Call"
          value={
            total?.total_calls > 0
              ? Math.round(total.total_tokens / total.total_calls).toLocaleString()
              : "0"
          }
        />
      </div>

      {/* Daily usage */}
      <div className="dashboard-section">
        <h2 className="section-title">📈 Daily Token Usage (last 7 days)</h2>
        {daily.length === 0 ? (
          <p className="empty-state">No usage data yet.</p>
        ) : (
          <div className="mini-bars">
            {daily.map((d) => (
              <MiniBar
                key={d.date}
                label={new Date(d.date).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}
                value={d.total_tokens}
                max={maxDailyTokens}
              />
            ))}
          </div>
        )}
      </div>

      {/* Per chat usage */}
      <div className="dashboard-section">
        <h2 className="section-title">💬 Token Usage by Chat</h2>
        {byChat.length === 0 ? (
          <p className="empty-state">No chat data yet.</p>
        ) : (
          <div className="mini-bars">
            {byChat.map((c) => (
              <MiniBar
                key={c.chat_id}
                label={c.title || "Untitled Chat"}
                value={c.total_tokens}
                max={maxChatTokens}
              />
            ))}
          </div>
        )}
      </div>

      {/* Error log */}
      <div className="dashboard-section">
        <h2 className="section-title">⚠️ Recent Errors</h2>
        {errors.length === 0 ? (
          <p className="empty-state">✅ No errors logged.</p>
        ) : (
          <div className="error-table">
            <div className="error-table-header">
              <span>Time</span>
              <span>Type</span>
              <span>Message</span>
            </div>
            {errors.map((e, i) => (
              <div key={i} className="error-row">
                <span className="error-time">
                  {new Date(e.created_at).toLocaleString()}
                </span>
                <span className="error-type">{e.error_type}</span>
                <span className="error-msg">{e.error_msg}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}