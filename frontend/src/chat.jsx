import { useState, useEffect, useRef, useCallback } from "react";
import MarkdownContent, { splitToolCalls } from "./MarkdownContent";
import { IconSend, IconStop } from "./Icons";
import { authFetch, getToken, API_URL } from "./api";
const SUGGESTED_PROMPTS = [
  "What's the weather in Tokyo for the next 5 days?",
  "Tell me about travel to Japan — currency, language, visa tips",
  "Find top restaurants in Paris",
  "Plan a 3-day budget trip to Bangkok",
  "Find museums in Rome",
];

function ToolCall({ name, args }) {
  return (
    <div className="tool-call">
      <span className="tool-call-dot" />
      <span>
        Using <span className="tool-call-name">{name}</span>
        {args && <span className="tool-call-args">({args})</span>}
      </span>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="typing-indicator">
      <span className="typing-dot" />
      <span className="typing-dot" />
      <span className="typing-dot" />
    </div>
  );
}

function AssistantMessage({ content, streaming }) {
  if (streaming) {
    return (
      <div className="message message--assistant">
        <div className="message-body">
          <div className="message-label">Assistant</div>
          {!content ? (
            <TypingIndicator />
          ) : (
            <pre className="streaming-text">{content}</pre>
             
          )}
        </div>
      </div>
    );
  }

  const parts = splitToolCalls(content);

  return (
    <div className="message message--assistant">
      <div className="message-body">
        <div className="message-label">Assistant</div>
        {parts.map((part, i) => {
          if (part.type === "tool") {
            return <ToolCall key={i} name={part.name} args={part.args} />;
          }
          if (!part.content.trim()) return null;
          return (
            <div key={i} className="markdown-body">
              <MarkdownContent content={part.content} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function UserMessage({ content }) {
  return (
    <div className="message message--user">
      <div className="message-body">{content}</div>
    </div>
  );
}

export default function Chat({ chatId, chatTitle, onTitleUpdate }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [isFirstMessage, setIsFirstMessage] = useState(true);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    return () => {
      authFetch(`/chat/${chatId}/end-session`, {
        method: "POST",
        keepalive: true,
      });
    };
  }, [chatId]);

  useEffect(() => {
    async function loadChatHistory() {
      try {
        const res = await authFetch(`/chat/${chatId}/messages`);
        if (res.ok) {
          const data = await res.json();
          setMessages(data);
          setIsFirstMessage(data.length === 0);
        }
      } catch (e) {
        console.error("Failed to load chat history", e);
      }
    }
    loadChatHistory();
  }, [chatId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [chatId]);

  const persistTitle = useCallback(
    async (title) => {
      onTitleUpdate(title);
      try {
        await authFetch(`/chat/${chatId}`, {
          method: "PATCH",
          body: JSON.stringify({ title }),
        });
      } catch (e) {
        console.error("Failed to save title", e);
      }
    },
    [chatId, onTitleUpdate]
  );
  const sendMessage = useCallback(
    async (text) => {
      const userText = (text || input).trim();
      if (!userText || isStreaming) return;

      setInput("");
      setIsStreaming(true);

      const assistantId = Date.now();

       setMessages((prev) => [
           ...prev,
           { role: "user", content: userText },
           { role: "assistant", content: "", streaming: true, id: assistantId },
    ]);

      
      try {
        const res = await authFetch(`/chat/${chatId}/message`, {
          method: "POST",
          body: JSON.stringify({
            message: userText,
            is_new_chat: isFirstMessage,
          }),
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setIsFirstMessage(false);

        // Read full response

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullText = "";
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          console.log("RAW:", decoder.decode(value || new Uint8Array(), { stream: true }));
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop(); // keep incomplete line in buffer

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const chunk = line.slice(6);
            console.log("CHUNK:", JSON.stringify(chunk));

            if (chunk.trim() === "[DONE]") {
              continue;
            }
            if (chunk.startsWith("[ERROR]")) {
              fullText += `\n\n**Error:** ${chunk.slice(7)}`;
              break;
            }
            if (chunk) {
              console.log("CHUNK:", chunk);
              fullText += chunk;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: fullText, streaming: true }
                    : m
                )
              );
            }
          }
        }

        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: fullText, streaming: false }
              : m
          )
        );

        if (fullText.length > 30) {
          const autoTitle = userText.length > 48 ? userText.slice(0, 48) + "…" : userText;
          persistTitle(autoTitle);
        }

      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: "**Connection error.** Please try again.", streaming: false }
              : m
          )
        );
      } finally {
        setIsStreaming(false);
        inputRef.current?.focus();
      }
    },
    [input, isStreaming, chatId, isFirstMessage, persistTitle]
  );


  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function handleStop() {
    setIsStreaming(false);
  }

  return (
    <div className="chat-container">
      <header className="chat-header">
        <h2 className="chat-header-title">{chatTitle || "New Chat"}</h2>
      </header>

      <div className="messages-area">
        <div className="messages-inner">
          {messages.length === 0 && (
            <div className="empty-chat">
              <h2>Where to next?</h2>
              <p>Ask about weather, destinations, places, or trip planning.</p>
              <div className="suggested-prompts">
                {SUGGESTED_PROMPTS.map((p) => (
                  <button
                    key={p}
                    className="suggested-prompt"
                    onClick={() => sendMessage(p)}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) =>
            msg.role === "user" ? (
              <UserMessage key={msg.id || i} content={msg.content} />
            ) : (
              <AssistantMessage
                key={msg.id || i}
                content={msg.content}
                streaming={msg.streaming}
              />
            )
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="input-bar">
        <div className="input-bar-inner">
          <textarea
            ref={inputRef}
            className="chat-input"
            rows={1}
            placeholder="Message Travel Assistant…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isStreaming}
          />
          {isStreaming ? (
            <button className="btn-stop" onClick={handleStop} title="Stop generating">
              <IconStop />
            </button>
          ) : (
            <button
              className="btn-send"
              onClick={() => sendMessage()}
              disabled={!input.trim()}
              title="Send message"
            >
              <IconSend />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}