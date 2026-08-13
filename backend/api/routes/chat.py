import asyncio
import json
import logging
import re

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config.settings import settings
from rag.llm_client import stream_tokens
from rag.prompts import build_prompt, no_context_template, empty_db_template
from rag.rag_chain import retrieve_context, get_retriever
from services.conversation_store import (
    append_session_message,
    get_session_history,
    prepare_regeneration,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _contains_trigger(text: str, trigger: str) -> bool:
    if " " in trigger:
        return trigger in text
    return re.search(rf"\b{re.escape(trigger)}\b", text) is not None


class ChatRequest(BaseModel):
    session_id: str
    question: str
    stream: bool = True
    instructions: str = ""
    language: str = ""
    regenerate: bool = False
    document_name: str = Field(default="", max_length=180)


async def _retrieve_nodes(
    question: str,
    rewritten_question: str,
    user_id: str,
    document_name: str = "",
):
    try:
        nodes = await asyncio.to_thread(
            retrieve_context,
            rewritten_question,
            user_id,
            settings.TOP_K,
            True,
            document_name,
        )
        if not nodes:
            nodes = await asyncio.to_thread(
                retrieve_context,
                question,
                user_id,
                settings.TOP_K,
                True,
                document_name,
            )
    except FileNotFoundError:
        nodes = []
    except Exception as exc:
        logger.error("Retrieval error: %s", exc)
        nodes = []
    return nodes


async def generate_stream(prompt: str, extra_events: list[dict] | None = None):
    batch: list[str] = []
    async for token in stream_tokens(prompt):
        batch.append(token)
        if len(batch) >= 3:
            yield f"data: {json.dumps({'token': ''.join(batch)})}\n\n"
            batch.clear()
    if batch:
        yield f"data: {json.dumps({'token': ''.join(batch)})}\n\n"
    if extra_events:
        for event in extra_events:
            yield f"data: {json.dumps(event)}\n\n"
    yield "data: [DONE]\n\n"


async def single_token_stream(text: str):
    yield f"data: {json.dumps({'token': text})}\n\n"
    yield "data: [DONE]\n\n"


@router.post("")
@router.post("/stream")
async def chat_stream(http_request: Request, request: ChatRequest):
    user_id = getattr(http_request.state, "user_id", "") or "__anonymous__"
    session_id = request.session_id
    question = request.question.strip()
    language = request.language.strip().lower() if request.language else ""
    document_name = request.document_name.strip()

    if not question:
        return StreamingResponse(
            single_token_stream("Please enter a question."),
            media_type="text/event-stream",
        )

    if request.regenerate:
        prepare_regeneration(session_id, user_id)

    question_lower = question.lower().strip()
    greetings = ["hello", "hi", "hey", "greetings", "good morning", "good afternoon", "good evening"]
    if any(re.search(r'\b' + re.escape(greeting) + r'\b', question_lower) for greeting in greetings):
        greeting_response = "Hi! I'm Nova — your intelligent research companion. What would you like to explore today?"
        if not request.regenerate:
            append_session_message(session_id, "user", question, user_id)
        append_session_message(session_id, "assistant", greeting_response, user_id)
        return StreamingResponse(
            single_token_stream(greeting_response),
            media_type="text/event-stream",
        )

    history = get_session_history(session_id, user_id)[-settings.MAX_HISTORY_MESSAGES :]

    rewritten_question = question
    trigger_words = [
        "it", "this", "that", "they", "them", "its", "their", "these", "those",
        "nó", "cái này", "cái đó", "những cái này", "những cái đó", "chúng", "chúng nó",
        "cụ thể", "chi tiết", "cụ thể hơn", "rõ hơn", "kể tiếp", "tiếp theo", "nói rõ",
    ]
    if history and (
        any(_contains_trigger(question_lower, word) for word in trigger_words)
        or len(question.split()) <= 3
    ):
        history_text = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in history)
        rewritten_question = f"{question} (Previous context: {history_text})"

    nodes = await _retrieve_nodes(question, rewritten_question, user_id, document_name)
    has_docs = False
    try:
        retriever = get_retriever(user_id)
        has_docs = len(retriever.documents) > 0 if retriever else False
    except Exception:
        has_docs = False

    if not language:
        vietnamese_chars = re.search(r'[àáạãảâầấậẫẩăằắặẵẳđèéẹẽẻêềếệễểìíịĩỉòóọõỏôồốộỗổơờớợỡỡùúụũủưừứựữửỳýỵỹỷ]', question.lower())
        language = "vietnamese" if vietnamese_chars else "english"

    lang_instruction = ""
    if language == "english":
        lang_instruction = "CRITICAL: You MUST respond in English regardless of the user's language."
    elif language == "vietnamese":
        lang_instruction = "CRITICAL: You MUST respond in Vietnamese regardless of the user's language."

    if not nodes and has_docs:
        history_text = "\n".join(
            f"{m['role']}: {m['content'][:300]}"
            for m in history[-settings.MAX_HISTORY_MESSAGES :]
        )
        instructions = request.instructions or "No specific instructions."
        if lang_instruction:
            instructions = f"{lang_instruction}\n\n{instructions}"
        prompt = no_context_template.format(
            question=question,
            history=history_text,
            instructions=instructions,
        )
        no_context_found = True
    elif not nodes and not has_docs:
        instructions = request.instructions or "No specific instructions."
        if lang_instruction:
            instructions = f"{lang_instruction}\n\n{instructions}"
        prompt = empty_db_template.format(
            question=question,
            instructions=instructions,
        )
        no_context_found = True
    else:
        prompt = build_prompt(question, nodes, history, request.instructions, lang_instruction)
        no_context_found = False

    logger.info("Prompt length: %d chars, retrieved %d nodes, no_context_found=%s", len(prompt), len(nodes), no_context_found)

    if not request.regenerate:
        append_session_message(session_id, "user", question, user_id)

    async def sse_generator():
        full_response = ""
        extra = [{"action": "search_offer", "query": question}] if no_context_found else None
        async for chunk in generate_stream(prompt, extra_events=extra):
            if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                try:
                    data = json.loads(chunk[6:])
                    if "token" in data:
                        full_response += data["token"]
                except Exception:
                    pass
            yield chunk

        fallback = "I apologize, but I couldn't generate a response. Please try again."
        final_response = full_response or fallback
        history.append({"role": "assistant", "content": final_response})
        append_session_message(session_id, "assistant", final_response, user_id)

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
