-- ============================================================
-- Travel Assistant Memory Schema
-- ============================================================
CREATE EXTENSION IF NOT EXISTS vector;

-- User accounts — email/password auth
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Session registry — one row per chat, scoped by user
CREATE TABLE IF NOT EXISTS chats (
    chat_id     TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    title       TEXT DEFAULT 'New Chat',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (chat_id)
);

CREATE INDEX IF NOT EXISTS idx_chats_user ON chats(user_id);

-- ============================================================
-- SHORT-TERM: raw message turns
-- Scoped by (user_id, chat_id)
-- After 10 messages → summarize → delete those rows
-- ============================================================
CREATE TABLE IF NOT EXISTS messages (
    id              SERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL,
    chat_id         TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content         TEXT NOT NULL,
    message_index   INTEGER NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(user_id, chat_id);
CREATE INDEX IF NOT EXISTS idx_messages_index ON messages(user_id, chat_id, message_index);

-- ============================================================
-- MID-TERM: rolling chat summary
-- One row per (user_id, chat_id) — compounds over time
-- ============================================================
CREATE TABLE IF NOT EXISTS chat_summaries (
    user_id             TEXT NOT NULL,
    chat_id             TEXT NOT NULL,
    summary             TEXT NOT NULL,
    message_count_so_far INTEGER DEFAULT 0,
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, chat_id)
);

-- ============================================================
-- LONG-TERM: user preference profile
-- Scoped by user_id only — spans ALL their chats
-- ============================================================
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id          TEXT NOT NULL,
    preference_key   TEXT NOT NULL,
    preference_value TEXT NOT NULL,
    updated_at       TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, preference_key)
);

CREATE INDEX IF NOT EXISTS idx_profiles_user ON user_profiles(user_id);

CREATE TABLE IF NOT EXISTS user_facts (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    fact        TEXT NOT NULL,
    embedding   vector(384),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_facts_user ON user_facts(user_id);