import asyncio
import json
import logging
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config.settings import settings
from rag.llm_client import LLMStreamError, stream_tokens
from rag.prompts import build_prompt, build_context_and_evidence, no_context_template, empty_db_template, unknown_citation_ids
from rag.rag_chain import retrieve_context, get_retriever, rewrite_question
from services.conversation_store import (
    append_session_message,
    get_session_history,
    prepare_regeneration,
)
from services.account_lifecycle import AccountDeletionPending

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=36, pattern=r"^[A-Za-z0-9_-]+$")
    question: str = Field(min_length=1, max_length=8000)
    stream: bool = True
    instructions: str = Field(default="", max_length=4000)
    language: Literal["", "auto", "english", "vietnamese"] = ""
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
    except AccountDeletionPending:
        # Keep the actionable account-cleanup conflict rather than reporting
        # it as a transient index outage that ordinary chat retry could fix.
        raise
    except Exception as exc:
        logger.error("Retrieval error: %s", exc)
        raise HTTPException(status_code=503, detail="Document index is temporarily unavailable") from exc
    return nodes


async def generate_stream(prompt: str, extra_events: list[dict] | None = None):
    batch: list[str] = []
    has_tokens = False
    try:
        async for token in stream_tokens(prompt):
            has_tokens = has_tokens or bool(token)
            batch.append(token)
            if len(batch) >= 3:
                yield f"data: {json.dumps({'token': ''.join(batch)})}\n\n"
                batch.clear()
    except Exception:
        # Preserve text already produced before a provider failure, including
        # a short final batch. Cancellation is deliberately not caught here.
        if batch:
            yield f"data: {json.dumps({'token': ''.join(batch)})}\n\n"
        raise
    if batch:
        yield f"data: {json.dumps({'token': ''.join(batch)})}\n\n"
    if not has_tokens:
        raise RuntimeError("The provider returned an empty response")
    if extra_events:
        for event in extra_events:
            yield f"data: {json.dumps(event)}\n\n"
    yield "data: [DONE]\n\n"


async def single_token_stream(text: str):
    yield f"data: {json.dumps({'token': text})}\n\n"
    yield "data: [DONE]\n\n"


_STREAM_RESPONSES = {200: {
    "description": "Server-sent events; only [DONE] confirms a completed answer.",
    "content": {"text/event-stream": {"schema": {"type": "string"}}},
}}


@router.post("", response_class=StreamingResponse, responses=_STREAM_RESPONSES)
@router.post("/stream", response_class=StreamingResponse, responses=_STREAM_RESPONSES)
async def chat_stream(http_request: Request, request: ChatRequest):
    user_id = getattr(http_request.state, "user_id", "") or "__anonymous__"
    session_id = request.session_id
    question = request.question.strip()
    language = "" if request.language in {"", "auto"} else request.language
    document_name = request.document_name.strip()

    if not question:
        return StreamingResponse(
            single_token_stream("Please enter a question."),
            media_type="text/event-stream",
        )

    if request.regenerate:
        prepare_regeneration(session_id, user_id, question=question)
        # A request may have failed before the original user turn reached the
        # server. Regenerate reuses a matching last turn, or creates it once.
        prior = get_session_history(session_id, user_id)
        if not prior or prior[-1] != {"role": "user", "content": question}:
            append_session_message(session_id, "user", question, user_id)

    question_lower = question.lower().strip()
    greetings = {"hello", "hi", "hey", "greetings", "good morning", "good afternoon", "good evening", "xin chào", "chào"}
    greeting_only = re.sub(r"[.!?,;:]+$", "", question_lower).strip()
    if greeting_only in greetings:
        vietnamese = language == "vietnamese" or (not language and greeting_only in {"xin chào", "chào"})
        greeting_response = (
            "Chào bạn! Mình là Nova. Bạn muốn tìm hiểu nội dung nào trong tài liệu?"
            if vietnamese else "Hi! I'm Nova — your intelligent research companion. What would you like to explore today?"
        )
        if not request.regenerate:
            append_session_message(session_id, "user", question, user_id)
        append_session_message(session_id, "assistant", greeting_response, user_id)
        return StreamingResponse(
            single_token_stream(greeting_response),
            media_type="text/event-stream",
        )

    history = get_session_history(session_id, user_id)[-settings.MAX_HISTORY_MESSAGES :]

    rewritten_question = rewrite_question(question, history)

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
        evidence = build_context_and_evidence(nodes, question)[1]
        yield f"data: {json.dumps({'evidence': evidence})}\n\n"
        extra = [{"action": "search_offer", "query": question}] if no_context_found else None
        completed = False
        try:
            async for chunk in generate_stream(prompt, extra_events=extra):
                if chunk == "data: [DONE]\n\n":
                    if unknown_citation_ids(full_response, evidence):
                        raise LLMStreamError("The provider cited an unknown evidence ID")
                    # Commit the answer and its evidence before acknowledging
                    # completion to the browser.
                    append_session_message(session_id, "assistant", full_response, user_id, evidence=evidence)
                    completed = True
                elif chunk.startswith("data: "):
                    data = json.loads(chunk[6:])
                    full_response += data.get("token", "")
                yield chunk
        except Exception:
            logger.exception("Chat stream failed")
            yield f"data: {json.dumps({'error': 'Response interrupted. Regenerate the answer to try again.'})}\n\n"
        finally:
            if not completed:
                try:
                    append_session_message(session_id, "assistant", full_response, user_id, evidence=evidence, interrupted=True)
                except AccountDeletionPending:
                    # Cleanup deliberately prevents a delayed response from
                    # recreating history. The interrupted stream is already
                    # reported to the browser; do not retry the blocked write.
                    logger.info("Skipped interrupted-response persistence for a deleting account")

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
