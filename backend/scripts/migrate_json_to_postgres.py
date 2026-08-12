"""One-time import of legacy JSON users/conversations into DATABASE_URL."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from services.database import ConversationRecord, UserRecord, database_session

BACKEND_DIR = Path(__file__).resolve().parents[1]


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="validate and count without committing")
    args = parser.parse_args()
    users = load_json(BACKEND_DIR / "storage" / "users.json", {})
    imported_users = 0
    imported_conversations = 0
    with database_session() as session:
        for username, payload in users.items():
            user_id = payload.get("user_id")
            username_exists = session.scalar(
                select(UserRecord.id).where(UserRecord.username == username)
            )
            if not user_id or session.get(UserRecord, user_id) or username_exists:
                continue
            session.add(UserRecord(
                id=user_id,
                username=username,
                password_hash=payload["password_hash"],
                created_at=float(payload.get("created_at", 0)),
            ))
            imported_users += 1
        session.flush()

        for user_id in [payload.get("user_id") for payload in users.values()]:
            if not user_id or not session.get(UserRecord, user_id):
                continue
            path = BACKEND_DIR / "storage" / "sessions" / user_id / "conversations.json"
            for conversation_id, payload in load_json(path, {}).items():
                existing = session.scalar(select(ConversationRecord.id).where(ConversationRecord.id == conversation_id))
                if existing:
                    continue
                session.add(ConversationRecord(
                    id=conversation_id,
                    user_id=user_id,
                    title=str(payload.get("title", "New Chat"))[:120],
                    messages=payload.get("messages", []) if isinstance(payload.get("messages", []), list) else [],
                    pinned=bool(payload.get("pinned", False)),
                    created_at=float(payload.get("createdAt", 0)),
                    updated_at=float(payload.get("updatedAt", 0)),
                ))
                imported_conversations += 1

        if args.dry_run:
            session.rollback()

    verb = "Validated" if args.dry_run else "Imported"
    print(f"{verb} {imported_users} users and {imported_conversations} conversations")


if __name__ == "__main__":
    main()
