"""
main.py — FastAPI entry point

Auth:
  POST /auth/register          → create account
  POST /auth/login             → get JWT token
  GET  /auth/me                → current user info

Chat (requires auth):
  POST /chat/start             → create a new chat session
  GET  /chat/list              → list user's chats
  POST /chat/{chat_id}/message → send a message (SSE stream)
  GET  /chat/preferences       → get long-term user profile
  DELETE /chat/{chat_id}       → delete a chat
"""

import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from starlette.responses import StreamingResponse
from agent import run_agent_streaming
from auth import (
    User,
    authenticate_user,
    create_access_token,
    ensure_users_table,
    get_current_user,
    register_user,
    verify_chat_owner,
)
from memory import (
    create_chat,
    list_chats,
    load_memory,
    get_pool,
    extract_and_save_facts,
    fetch_recent_messages,
    update_chat_title,
)

if not os.environ.get("GROQ_API_KEY"):
    raise RuntimeError("GROQ_API_KEY is not set")
if not os.environ.get("GEOAPIFY_KEY"):
    raise RuntimeError("GEOAPIFY_KEY is not set")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_users_table()
    yield


app = FastAPI(title="Travel Assistant API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth schemas ──────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    interests: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str


class UserResponse(BaseModel):
    user_id: str
    email: str


# ── Chat schemas ──────────────────────────────────────────────────────────────
class StartChatRequest(BaseModel):
    title: str = "New Chat"


class StartChatResponse(BaseModel):
    chat_id: str
    title: str


class MessageRequest(BaseModel):
    message: str
    is_new_chat: bool = False


class RenameChatRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


# ── Auth endpoints ────────────────────────────────────────────────────────────
@app.post("/auth/register", response_model=AuthResponse)
async def register(body: RegisterRequest):
    user = await register_user(body.email, body.password, body.interests or None)
    token = create_access_token(user.id, user.email)
    return AuthResponse(access_token=token, user_id=user.id, email=user.email)


@app.post("/auth/login", response_model=AuthResponse)
async def login(body: LoginRequest):
    user = await authenticate_user(body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user.id, user.email)
    return AuthResponse(access_token=token, user_id=user.id, email=user.email)


@app.get("/auth/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return UserResponse(user_id=user.id, email=user.email)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Chat management ───────────────────────────────────────────────────────────
@app.post("/chat/start", response_model=StartChatResponse)
async def start_chat(body: StartChatRequest, user: User = Depends(get_current_user)):
    chat_id = str(uuid.uuid4())
    await create_chat(user.id, chat_id, body.title)
    return StartChatResponse(chat_id=chat_id, title=body.title)


@app.get("/chat/list")
async def get_chats(user: User = Depends(get_current_user)):
    chats = await list_chats(user.id)
    return [
        {
            "chat_id": c.chat_id,
            "title": c.title,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in chats
    ]


@app.get("/chat/preferences")
async def get_preferences(user: User = Depends(get_current_user)):
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT preference_key, preference_value FROM user_profiles WHERE user_id=$1",
        user.id,
    )
    return {r["preference_key"]: r["preference_value"] for r in rows}


@app.delete("/chat/{chat_id}")
async def delete_chat(chat_id: str, user: User = Depends(get_current_user)):
    await verify_chat_owner(user.id, chat_id)
    pool = await get_pool()
    await pool.execute("DELETE FROM messages WHERE chat_id=$1 AND user_id=$2", chat_id, user.id)
    await pool.execute("DELETE FROM chat_summaries WHERE chat_id=$1 AND user_id=$2", chat_id, user.id)
    await pool.execute("DELETE FROM chats WHERE chat_id=$1 AND user_id=$2", chat_id, user.id)
    return {"deleted": chat_id}


@app.patch("/chat/{chat_id}")
async def rename_chat(
    chat_id: str,
    body: RenameChatRequest,
    user: User = Depends(get_current_user),
):
    await verify_chat_owner(user.id, chat_id)
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    await update_chat_title(chat_id, title)
    return {"chat_id": chat_id, "title": title}

@app.get("/chat/{chat_id}/messages")
async def get_messages(chat_id: str, user: User = Depends(get_current_user)):
    await verify_chat_owner(user.id, chat_id)
    try:
        messages = await fetch_recent_messages(user.id, chat_id)
        return [
            {
                "role": m.role,
                "content": m.content,
                "message_index": m.message_index,
            }
            for m in messages
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── SSE streaming message endpoint ───────────────────────────────────────────
@app.post("/chat/{chat_id}/message")
async def send_message(
    chat_id: str,
    body: MessageRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if not body.is_new_chat:
        await verify_chat_owner(user.id, chat_id)

    async def generate():
        try:
            async for chunk in run_agent_streaming(
                user_id=user.id,
                chat_id=chat_id,
                user_input=body.message,
                is_new_chat=body.is_new_chat,
            ):
                yield f"data: {chunk}\n\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: [ERROR] {str(e)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/chat/{chat_id}/end-session")
async def end_session(chat_id: str, user: User = Depends(get_current_user)):
    await verify_chat_owner(user.id, chat_id)
    await extract_and_save_facts(user.id, chat_id)
    return {"status": "facts saved"}


# ── Memory debug endpoints ────────────────────────────────────────────────────
@app.get("/debug/{chat_id}/memory")
async def debug_memory(chat_id: str, user: User = Depends(get_current_user)):
    """Show all three memory tiers for a chat — useful for debugging."""
    await verify_chat_owner(user.id, chat_id)
    ctx = await load_memory(user.id, chat_id)
    pool = await get_pool()
    fact_rows = await pool.fetch(
        "SELECT fact FROM user_facts WHERE user_id = $1 ORDER BY created_at DESC",
        user.id,
    )
    return {
        "short_term_messages": [
            {"role": m.role, "content": m.content[:200], "index": m.message_index}
            for m in ctx.recent_messages
        ],
        "mid_term_summary": ctx.chat_summary,
        "long_term_preferences": ctx.user_preferences,
        "long_term_facts": [r["fact"] for r in fact_rows],
        "next_message_index": ctx.next_message_index,
    }

# ── Observability endpoints ───────────────────────────────────────────────────
@app.get("/usage/me/total")
async def get_my_total_usage(user: User = Depends(get_current_user)):
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT 
            COALESCE(SUM(input_tokens), 0) as total_input,
            COALESCE(SUM(output_tokens), 0) as total_output,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COUNT(*) as total_calls
        FROM llm_usage WHERE user_id = $1
        """,
        user.id,
    )
    return dict(row)


@app.get("/usage/me/daily")
async def get_my_daily_usage(user: User = Depends(get_current_user)):
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT 
            DATE(created_at) as date,
            COALESCE(SUM(input_tokens), 0) as input_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COUNT(*) as calls
        FROM llm_usage
        WHERE user_id = $1
        AND created_at >= NOW() - INTERVAL '30 days'
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        """,
        user.id,
    )
    return [dict(r) for r in rows]


@app.get("/usage/me/by-chat")
async def get_usage_by_chat(user: User = Depends(get_current_user)):
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT 
            u.chat_id,
            c.title,
            COALESCE(SUM(u.total_tokens), 0) as total_tokens,
            COUNT(*) as calls,
            MAX(u.created_at) as last_used
        FROM llm_usage u
        LEFT JOIN chats c ON c.chat_id = u.chat_id
        WHERE u.user_id = $1
        GROUP BY u.chat_id, c.title
        ORDER BY last_used DESC
        LIMIT 10
        """,
        user.id,
    )
    return [dict(r) for r in rows]


@app.get("/debug/errors")
async def get_errors(user: User = Depends(get_current_user)):
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT error_type, error_msg, chat_id, created_at
        FROM error_logs
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT 20
        """,
        user.id,
    )
    return [dict(r) for r in rows]