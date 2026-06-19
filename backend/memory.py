"""
memory.py — Three-tier memory over PostgreSQL

  Short-term  : messages table   — (user_id, chat_id)
  Mid-term    : chat_summaries   — (user_id, chat_id)  rolling summary
  Long-term   : user_profiles    — (user_id)            preference KV store

Public API
----------
  load_memory(user_id, chat_id)             → MemoryContext
  save_message(user_id, chat_id, role, content)
  maybe_summarize(user_id, chat_id)         → runs if ≥ 10 new messages
  extract_and_save_preferences(user_id, chat_id)
  list_chats(user_id)                       → list[ChatMeta]
  create_chat(user_id, chat_id, title)
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime

import asyncpg
from groq import AsyncGroq
from embeddings import get_embedding

# ── pgvector: user facts ──────────────────────────────────────────────────────
async def save_user_fact(user_id: str, fact: str) -> None:
    """Store a fact, skip if semantically similar fact already exists."""
    pool = await get_pool()

    embedding = get_embedding(fact)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    # Check if semantically similar fact exists (cosine distance < 0.15 = very similar)
    existing = await pool.fetchrow(
        """
        SELECT id FROM user_facts
        WHERE user_id = $1
        AND embedding <=> $2::vector < 0.3
        LIMIT 1
        """,
        user_id, embedding_str,
    )
    if existing:
        return  # Skip semantically duplicate

    await pool.execute(
        """
        INSERT INTO user_facts (user_id, fact, embedding, created_at)
        VALUES ($1, $2, $3::vector, NOW())
        """,
        user_id, fact, embedding_str,
    )
async def get_relevant_facts(
    user_id: str,
    query: str,
    top_k: int = 5,
    max_distance: float = 0.55,
) -> list[str]:
    """Find top-K facts semantically relevant to the query."""
    pool = await get_pool()
    query_embedding = get_embedding(query)
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    rows = await pool.fetch(
        """
        SELECT fact, embedding <=> $2::vector AS distance
        FROM user_facts
        WHERE user_id = $1
        AND embedding <=> $2::vector < $3
        ORDER BY embedding <=> $2::vector
        LIMIT $4
        """,
        user_id, embedding_str, max_distance, top_k,
    )
    return [r["fact"] for r in rows]


def _cosine_distance(a: list[float], b: list[float]) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1.0 - dot / (norm_a * norm_b)


async def get_facts_for_agent(
    user_id: str,
    user_input: str,
    summary: str = "",
    preferences: dict[str, str] | None = None,
    top_k: int = 5,
    max_distance: float = 0.55,
) -> list[str]:
    """Return only long-term facts/preferences relevant to the current prompt."""
    search_query = f"{user_input}\n{summary}".strip() or user_input
    if not search_query.strip():
        return []

    seen: set[str] = set()
    facts: list[str] = []

    def _add(fact: str) -> None:
        key = fact.lower().strip()
        if key and key not in seen:
            seen.add(key)
            facts.append(fact)

    for fact in await get_relevant_facts(
        user_id, search_query, top_k=top_k, max_distance=max_distance
    ):
        _add(fact)

    prefs = preferences if preferences is not None else await _fetch_preferences(user_id)
    if prefs:
        query_emb = get_embedding(search_query)
        for key, val in prefs.items():
            if not val:
                continue
            pref_fact = f"User's {key.replace('_', ' ')}: {val}"
            dist = _cosine_distance(query_emb, get_embedding(pref_fact))
            if dist < max_distance:
                _add(pref_fact)

    return facts


async def extract_and_save_facts(user_id: str, chat_id: str) -> None:
    """
    Extract discrete facts from conversation and store with embeddings.
    Replaces extract_and_save_preferences for semantic search.
    """
    messages = await fetch_recent_messages(user_id, chat_id)
    summary, _ = await _fetch_summary(user_id, chat_id)

    context = ""
    if summary:
        context += f"Chat summary:\n{summary}\n\n"
    if messages:
        context += "Recent messages:\n" + "\n".join(
            f"{m.role.upper()}: {m.content}" for m in messages[-20:]
        )

    if not context.strip():
        return

    prompt = (
        "Extract discrete facts about this user's travel preferences from the conversation. "
        "Return a JSON array of short fact strings. "
        "Each fact should be a single sentence like: "
        "'User is vegetarian', 'User prefers budget hostels', 'User loves museums and history', "
        "'User has a budget of $1000', 'User wants to visit Japan in December'. "
        "Only include facts clearly stated or strongly implied. "
        "Return ONLY a valid JSON array, no markdown, no explanation.\n\n"
        + context
    )

    client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
    resp = await client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = resp.choices[0].message.content.strip()
    try:
        raw = raw.replace("```json", "").replace("```", "").strip()
        facts = json.loads(raw)
        for fact in facts:
            if isinstance(fact, str) and fact.strip():
                await save_user_fact(user_id, fact.strip())
    except json.JSONDecodeError:
        pass

# ── DB pool ──────────────────────────────────────────────────────────────────
_pool: asyncpg.Pool | None = None

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=os.environ["DATABASE_URL"],
            min_size=2,
            max_size=10,
        )
    return _pool


# ── Data classes ─────────────────────────────────────────────────────────────
@dataclass
class MessageRow:
    role: str
    content: str
    message_index: int

@dataclass
class MemoryContext:
    """Everything the agent needs at the start of a turn."""
    recent_messages: list[MessageRow] = field(default_factory=list)
    chat_summary: str = ""
    user_preferences: dict[str, str] = field(default_factory=dict)
    next_message_index: int = 0

@dataclass
class ChatMeta:
    chat_id: str
    title: str
    created_at: datetime
    updated_at: datetime


# ── Chat registry ─────────────────────────────────────────────────────────────
async def create_chat(user_id: str, chat_id: str, title: str = "New Chat") -> None:
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO chats (chat_id, user_id, title, created_at, updated_at)
        VALUES ($1, $2, $3, NOW(), NOW())
        ON CONFLICT (chat_id) DO NOTHING
        """,
        chat_id, user_id, title,
    )

async def update_chat_title(chat_id: str, title: str) -> None:
    pool = await get_pool()
    await pool.execute(
        "UPDATE chats SET title=$1, updated_at=NOW() WHERE chat_id=$2",
        title, chat_id,
    )

async def list_chats(user_id: str) -> list[ChatMeta]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT chat_id, title, created_at, updated_at FROM chats WHERE user_id=$1 ORDER BY updated_at DESC",
        user_id,
    )
    return [ChatMeta(**dict(r)) for r in rows]


# ── Short-term: messages ───────────────────────────────────────────────────────
async def save_message(user_id: str, chat_id: str, role: str, content: str) -> int:
    """Append a message and return its index."""
    pool = await get_pool()

    # Get next index
    row = await pool.fetchrow(
        "SELECT COALESCE(MAX(message_index), -1) + 1 AS next FROM messages WHERE user_id=$1 AND chat_id=$2",
        user_id, chat_id,
    )
    idx = row["next"]

    await pool.execute(
        """
        INSERT INTO messages (user_id, chat_id, role, content, message_index, created_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
        """,
        user_id, chat_id, role, content, idx,
    )

    # Touch chat updated_at
    await pool.execute(
        "UPDATE chats SET updated_at=NOW() WHERE chat_id=$1",
        chat_id,
    )
    return idx

async def fetch_recent_messages(user_id: str, chat_id: str) -> list[MessageRow]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT role, content, message_index
        FROM messages
        WHERE user_id=$1 AND chat_id=$2
        ORDER BY message_index ASC
        """,
        user_id, chat_id,
    )
    return [MessageRow(role=r["role"], content=r["content"], message_index=r["message_index"]) for r in rows]

async def _count_messages(user_id: str, chat_id: str) -> int:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT COUNT(*) AS n FROM messages WHERE user_id=$1 AND chat_id=$2",
        user_id, chat_id,
    )
    return row["n"]


# ── Mid-term: rolling chat summary ────────────────────────────────────────────
async def _fetch_summary(user_id: str, chat_id: str) -> tuple[str, int]:
    """Returns (summary_text, message_count_so_far)."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT summary, message_count_so_far FROM chat_summaries WHERE user_id=$1 AND chat_id=$2",
        user_id, chat_id,
    )
    if not row:
        return "", 0
    return row["summary"], row["message_count_so_far"]

async def _upsert_summary(user_id: str, chat_id: str, summary: str, total_count: int) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO chat_summaries (user_id, chat_id, summary, message_count_so_far, updated_at)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (user_id, chat_id) DO UPDATE
          SET summary=EXCLUDED.summary,
              message_count_so_far=EXCLUDED.message_count_so_far,
              updated_at=NOW()
        """,
        user_id, chat_id, summary, total_count,
    )

async def _delete_messages_up_to(user_id: str, chat_id: str, max_index: int) -> None:
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM messages WHERE user_id=$1 AND chat_id=$2 AND message_index <= $3",
        user_id, chat_id, max_index,
    )


SUMMARIZE_EVERY = 10  # messages before compaction

async def maybe_summarize(user_id: str, chat_id: str) -> None:
    """
    If there are ≥ SUMMARIZE_EVERY messages in short-term,
    compress them into the rolling summary and delete those rows.
    """
    messages = await fetch_recent_messages(user_id, chat_id)
    if len(messages) < SUMMARIZE_EVERY:
        return

    old_summary, prev_count = await _fetch_summary(user_id, chat_id)

    # Build conversation text for summarizer
    conv_text = "\n".join(f"{m.role.upper()}: {m.content}" for m in messages)

    prompt = (
        "You are a memory compactor for a travel assistant.\n\n"
        + (f"Previous running summary:\n{old_summary}\n\n" if old_summary else "")
        + f"New conversation to integrate:\n{conv_text}\n\n"
        "Write a concise updated summary (max 300 words) that captures:\n"
        "- Destinations discussed\n"
        "- User's travel dates, budget, preferences\n"
        "- Questions asked and answers given\n"
        "- Any plans or decisions made\n"
        "Output ONLY the summary text, no preamble."
    )
    client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
    resp = await client.chat.completions.create(
       model="meta-llama/llama-4-scout-17b-16e-instruct",
       max_tokens=400,
       messages=[{"role": "user", "content": prompt}],
    )
    new_summary = resp.choices[0].message.content.strip()
    

    max_idx = messages[-1].message_index
    total = prev_count + len(messages)

    await _upsert_summary(user_id, chat_id, new_summary, total)
    await _delete_messages_up_to(user_id, chat_id, max_idx)


# ── Long-term: user preferences ──────────────────────────────────────────────
async def _fetch_preferences(user_id: str) -> dict[str, str]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT preference_key, preference_value FROM user_profiles WHERE user_id=$1",
        user_id,
    )
    return {r["preference_key"]: r["preference_value"] for r in rows}

async def save_user_preference(user_id: str, key: str, value: str) -> None:
    """Public API for saving a user preference."""
    await _upsert_preference(user_id, key, value)


async def _upsert_preference(user_id: str, key: str, value: str) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO user_profiles (user_id, preference_key, preference_value, updated_at)
        VALUES ($1, $2, $3, NOW())
        ON CONFLICT (user_id, preference_key) DO UPDATE
          SET preference_value=EXCLUDED.preference_value, updated_at=NOW()
        """,
        user_id, key, value,
    )

async def extract_and_save_preferences(user_id: str, chat_id: str) -> None:
    """
    At end of session: run Claude over the last messages to extract
    durable user preferences and upsert them into user_profiles.
    """
    messages = await fetch_recent_messages(user_id, chat_id)
    summary, _ = await _fetch_summary(user_id, chat_id)

    context = ""
    if summary:
        context += f"Chat summary:\n{summary}\n\n"
    if messages:
        context += "Recent messages:\n" + "\n".join(
            f"{m.role.upper()}: {m.content}" for m in messages[-20:]
        )

    if not context.strip():
        return

    prompt = (
        "Extract durable travel preferences from this conversation. "
        "Return a JSON object with string keys and values. "
        "Keys should be short preference names like: budget, diet, travel_style, preferred_climate, "
        "home_city, interests, accommodation_type, travel_companions. "
        "Only include preferences that are clearly stated or strongly implied. "
        "Return ONLY valid JSON, no markdown, no explanation.\n\n"
        + context
    )

    client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
    resp = await client.chat.completions.create(
      model="meta-llama/llama-4-scout-17b-16e-instruct",
      max_tokens=300,
      messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.choices[0].message.content.strip()

    try:
        prefs = json.loads(raw)
        for key, val in prefs.items():
            if isinstance(key, str) and isinstance(val, str) and val:
                await _upsert_preference(user_id, key, val)
    except json.JSONDecodeError:
        pass  # Graceful — don't crash if extraction fails


# ── Main loader ───────────────────────────────────────────────────────────────
async def load_memory(user_id: str, chat_id: str) -> MemoryContext:
    """Load all three memory tiers in parallel."""
    messages_task = asyncio.create_task(fetch_recent_messages(user_id, chat_id))
    summary_task = asyncio.create_task(_fetch_summary(user_id, chat_id))
    prefs_task = asyncio.create_task(_fetch_preferences(user_id))

    messages, (summary, _), prefs = await asyncio.gather(
        messages_task, summary_task, prefs_task
    )

    next_idx = (messages[-1].message_index + 1) if messages else 0

    return MemoryContext(
        recent_messages=messages,
        chat_summary=summary,
        user_preferences=prefs,
        next_message_index=next_idx,
    )
