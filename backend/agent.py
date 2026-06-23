"""
agent.py — LangGraph single-node ReAct travel agent
"""

import os
import asyncio
from typing import AsyncIterator
from langchain_groq import ChatGroq
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from memory import (
    MemoryContext,
    create_chat,
    extract_and_save_facts,
    get_relevant_facts,
    load_memory,
    maybe_summarize,
    save_message,
)
from tools import TOOLS


os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "travel-assistant"

# ── Token budget helpers ──────────────────────────────────────────────────────
def _count_tokens(text: str) -> int:
    return len(text) // 4

def _apply_token_budget(
    facts: list[str],
    summary: str,
    messages: list,
    max_tokens: int = 3000,
) -> tuple[list[str], str, list]:
    FACTS_BUDGET = 500
    SUMMARY_BUDGET = 500
    MESSAGES_BUDGET = max_tokens - FACTS_BUDGET - SUMMARY_BUDGET

    trimmed_facts = []
    facts_tokens = 0
    for fact in facts:
        t = _count_tokens(fact)
        if facts_tokens + t <= FACTS_BUDGET:
            trimmed_facts.append(fact)
            facts_tokens += t

    trimmed_summary = summary
    if _count_tokens(summary) > SUMMARY_BUDGET:
        trimmed_summary = summary[:SUMMARY_BUDGET * 4] + "... [truncated]"

    trimmed_messages = []
    messages_tokens = 0
    for msg in reversed(messages):
        t = _count_tokens(msg.content or "")
        if messages_tokens + t <= MESSAGES_BUDGET:
            trimmed_messages.insert(0, msg)
            messages_tokens += t
        else:
            break

    return trimmed_facts, trimmed_summary, trimmed_messages

# ── Model ─────────────────────────────────────────────────────────────────────
_llm = ChatGroq(
    model="meta-llama/llama-4-scout-17b-16e-instruct",
    groq_api_key=os.environ["GROQ_API_KEY"],
    streaming=True,
    temperature=0.3,
    max_tokens=2048,
    model_kwargs={"parallel_tool_calls": False},
)

_graph = create_react_agent(_llm, tools=TOOLS)

def _format_memory_preamble(facts: list[str]) -> str:
    """Visible block shown to the user listing which stored facts are in play."""
    if not facts:
        return ""
    lines = "\n".join(f"• {f}" for f in facts)
    return f"🧠 **Using your saved preferences:**\n{lines}\n\n---\n\n"


# ── Prompt + message builders ─────────────────────────────────────────────────
async def _build_system_prompt(facts: list[str], summary: str) -> str:
    parts = [
        "You are a knowledgeable, friendly travel assistant. "
        "ALWAYS call tools when user asks about places, food, hotels, weather, or activities. "
        "NEVER make up place names or hotel names — only use results from tool calls. "
        "If a tool returns no results, say so honestly instead of inventing places or any other facts. "
        "Never ask permission to search — just search immediately and show results. "
        "Be concise and direct.",
    ]

    if facts:
        facts_text = "\n".join(f"  - {f}" for f in facts)
        parts.append(
            f"\n🧠 RELEVANT USER FACTS for this prompt — apply these:\n{facts_text}\n"
            "Rules for using stored facts:\n"
            "  1. Tailor recommendations to match the relevant facts above.\n"
            "  2. Only reference facts that apply to the current question.\n"
            "  3. After the preferences block already shown to the user, begin your reply with "
            "a short **Why I'm personalizing this:** section (2–4 bullets) explaining "
            "which of the above facts influenced your answer and how.\n"
            "  4. Do NOT mention or apply facts that are not relevant to this prompt."
        )

    if summary:
        parts.append(f"\n📋 Conversation summary:\n{summary}")

    return "\n".join(parts)


async def _build_message_list(
    ctx: MemoryContext,
    user_input: str,
    relevant_facts: list[str],
    summary: str,
    messages: list,
) -> list[BaseMessage]:
    system = SystemMessage(content=await _build_system_prompt(relevant_facts, summary))
    result: list[BaseMessage] = [system]

    for m in messages:
        if m.role == "user":
            result.append(HumanMessage(content=m.content))
        elif m.role == "assistant":
            result.append(AIMessage(content=m.content))

    result.append(HumanMessage(content=user_input))
    return result


# ── Public: streaming run ─────────────────────────────────────────────────────
async def run_agent_streaming(
    user_id: str,
    chat_id: str,
    user_input: str,
    is_new_chat: bool = False,
) -> AsyncIterator[str]:

    if is_new_chat:
        await create_chat(user_id, chat_id)
    ctx = await load_memory(user_id, chat_id)
    
    facts = await get_relevant_facts(user_id, user_input, top_k=8)
    trimmed_summary = ctx.chat_summary
    trimmed_messages = ctx.recent_messages

    messages = await _build_message_list(
        ctx,
        user_input,
        facts,
        trimmed_summary,
        trimmed_messages,
    )

    await save_message(user_id, chat_id, "user", user_input)

    full_response = []

    async for event in _graph.astream_events(
    {"messages": messages},
    version="v2",
    config={
        "metadata": {
            "thread_id": chat_id,
            "user_id": user_id,
            "conversation_id": chat_id,
        },
        "tags": [f"user:{user_id}", f"chat:{chat_id}"],
        "run_name": f"travel-agent-{chat_id[:8]}",
    }
):
        kind = event.get("event")

        if kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content"):
                content = chunk.content
                if isinstance(content, str) and content:
                    full_response.append(content)
                    print("TOKEN:", content)
                    yield content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            if text:
                                full_response.append(text)
                                yield text

        elif kind == "on_tool_start":
            tool_name = event.get("name", "tool")
            tool_input = event.get("data", {}).get("input", {})
            yield f"\n\n🔧 **Using {tool_name}**({', '.join(f'{k}={v}' for k,v in tool_input.items())})\n\n"

    assistant_reply = "".join(full_response).strip()
    if assistant_reply:
        await save_message(user_id, chat_id, "assistant", assistant_reply)

    await extract_and_save_facts(user_id, chat_id)
    await maybe_summarize(user_id, chat_id)