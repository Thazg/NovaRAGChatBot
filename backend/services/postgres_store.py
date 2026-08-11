from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import delete, select

from services.database import ConversationRecord, RefreshSessionRecord, UserRecord, database_session


def find_user_by_username(username: str) -> dict | None:
    with database_session() as session:
        user = session.scalar(select(UserRecord).where(UserRecord.username == username))
        return _user_dict(user) if user else None


def find_user_by_id(user_id: str) -> dict | None:
    with database_session() as session:
        user = session.get(UserRecord, user_id)
        return _user_dict(user) if user else None


def _user_dict(user: UserRecord) -> dict:
    return {
        "user_id": user.id,
        "username": user.username,
        "password_hash": user.password_hash,
        "created_at": user.created_at,
    }


def create_user(username: str, password_hash: str) -> dict | None:
    with database_session() as session:
        if session.scalar(select(UserRecord.id).where(UserRecord.username == username)):
            return None
        user = UserRecord(id=str(uuid.uuid4()), username=username, password_hash=password_hash, created_at=time.time())
        session.add(user)
        session.flush()
        return _user_dict(user)


def update_password(user_id: str, password_hash: str) -> None:
    with database_session() as session:
        user = session.get(UserRecord, user_id)
        if user:
            user.password_hash = password_hash


def delete_user_record(user_id: str) -> bool:
    with database_session() as session:
        user = session.get(UserRecord, user_id)
        if not user:
            return False
        session.delete(user)
        return True


def issue_refresh_session(token_hash: str, user_id: str, expires_at: float) -> None:
    with database_session() as session:
        session.add(RefreshSessionRecord(
            token_hash=token_hash,
            user_id=user_id,
            expires_at=expires_at,
            revoked=False,
            created_at=time.time(),
        ))


def consume_refresh_session(token_hash: str, user_id: str) -> bool:
    with database_session() as session:
        record = session.scalar(
            select(RefreshSessionRecord)
            .where(RefreshSessionRecord.token_hash == token_hash)
            .with_for_update()
        )
        if not record or record.user_id != user_id or record.revoked or record.expires_at <= time.time():
            return False
        record.revoked = True
        return True


def revoke_refresh_session(token_hash: str) -> None:
    with database_session() as session:
        record = session.get(RefreshSessionRecord, token_hash)
        if record:
            record.revoked = True


def _conversation_dict(record: ConversationRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "title": record.title,
        "messages": list(record.messages or []),
        "createdAt": int(record.created_at),
        "updatedAt": int(record.updated_at),
        "pinned": record.pinned,
    }


def get_conversation(conversation_id: str, user_id: str) -> dict[str, Any]:
    with database_session() as session:
        record = session.scalar(select(ConversationRecord).where(
            ConversationRecord.id == conversation_id,
            ConversationRecord.user_id == user_id,
        ))
        if not record:
            raise KeyError(conversation_id)
        return _conversation_dict(record)


def list_conversations(user_id: str) -> list[dict[str, Any]]:
    with database_session() as session:
        records = session.scalars(
            select(ConversationRecord)
            .where(ConversationRecord.user_id == user_id)
            .order_by(ConversationRecord.updated_at.desc())
        ).all()
        return [_conversation_dict(record) for record in records]


def create_conversation(user_id: str, title: str = "New Chat", conversation_id: str | None = None,
                        messages: list[dict[str, Any]] | None = None, pinned: bool = False) -> dict[str, Any]:
    conversation_id = conversation_id or str(uuid.uuid4())
    now = float(int(time.time() * 1000))
    with database_session() as session:
        existing = session.scalar(select(ConversationRecord).where(
            ConversationRecord.id == conversation_id,
            ConversationRecord.user_id == user_id,
        ))
        if existing:
            return _conversation_dict(existing)
        record = ConversationRecord(id=conversation_id, user_id=user_id, title=title.strip()[:120] or "New Chat",
                                    messages=messages or [], pinned=pinned, created_at=now, updated_at=now)
        session.add(record)
        session.flush()
        return _conversation_dict(record)


def mutate_conversation(conversation_id: str, user_id: str, mutation) -> dict[str, Any]:
    with database_session() as session:
        record = session.scalar(
            select(ConversationRecord).where(
                ConversationRecord.id == conversation_id,
                ConversationRecord.user_id == user_id,
            ).with_for_update()
        )
        if not record:
            raise KeyError(conversation_id)
        mutation(record)
        record.updated_at = float(int(time.time() * 1000))
        session.flush()
        return _conversation_dict(record)


def delete_conversation(conversation_id: str, user_id: str) -> None:
    with database_session() as session:
        result = session.execute(delete(ConversationRecord).where(
            ConversationRecord.id == conversation_id,
            ConversationRecord.user_id == user_id,
        ))
        if not result.rowcount:
            raise KeyError(conversation_id)


def clear_conversations(user_id: str) -> int:
    with database_session() as session:
        result = session.execute(delete(ConversationRecord).where(ConversationRecord.user_id == user_id))
        return int(result.rowcount or 0)
