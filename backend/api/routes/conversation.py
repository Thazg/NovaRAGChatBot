from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Literal
from uuid import UUID

from services.conversation_store import (
    create_conversation,
    clear_conversations,
    delete_conversation as delete_store_conversation,
    get_conversation,
    list_conversations as list_store_conversations,
    update_conversation,
)

router = APIRouter()


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    pinned: bool | None = None


class ConversationMessage(BaseModel):
    id: str | None = None
    role: Literal["user", "assistant", "system"]
    content: str = Field(max_length=200_000)
    createdAt: int | None = None


class ConversationCreate(BaseModel):
    id: UUID | None = None
    title: str = Field(default="New Chat", min_length=1, max_length=120)
    messages: list[ConversationMessage] = Field(default_factory=list, max_length=200)
    pinned: bool = False


def _get_user(request: Request) -> str:
    return getattr(request.state, "user_id", "") or "__anonymous__"


@router.get("")
def list_conversations(request: Request):
    return list_store_conversations(_get_user(request))


@router.post("/new")
def create_conversation_route(request: Request, body: ConversationCreate | None = None):
    body = body or ConversationCreate()
    return create_conversation(
        _get_user(request), body.title.strip(), str(body.id) if body.id else None,
        [message.model_dump(exclude_none=True) for message in body.messages], body.pinned
    )


@router.delete("")
def clear_conversations_route(request: Request):
    return {"status": "success", "deleted": clear_conversations(_get_user(request))}


@router.get("/{id}")
def get_conversation_route(request: Request, id: str):
    try:
        return get_conversation(id, _get_user(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc


@router.delete("/{id}")
def delete_conversation_route(request: Request, id: str):
    try:
        delete_store_conversation(id, _get_user(request))
        return {"status": "success"}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc


@router.put("/{id}")
def update_conversation_route(request: Request, id: str, update: ConversationUpdate):
    try:
        return update_conversation(id, _get_user(request), update.title, update.pinned)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
