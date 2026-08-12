from pathlib import Path

import pytest
from sqlalchemy import create_engine

from services import conversation_store, database, postgres_store


@pytest.fixture
def relational_store(monkeypatch):
    path = Path(__file__).with_name("_relational_test.db")
    path.unlink(missing_ok=True)
    engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False})
    database.Base.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    yield
    engine.dispose()
    path.unlink(missing_ok=True)


def test_relational_user_and_conversation_transactions(relational_store) -> None:
    user = postgres_store.create_user("database.user", "pbkdf2-hash")
    assert user is not None
    assert postgres_store.create_user("database.user", "other-hash") is None
    assert postgres_store.find_user_by_username("database.user")["user_id"] == user["user_id"]

    conversation = postgres_store.create_conversation(
        user["user_id"],
        conversation_id="6ab4ef03-50ba-4782-95db-ecc55d64c53d",
    )
    assert conversation["title"] == "New Chat"

    def add_message(record) -> None:
        record.messages = [{"role": "user", "content": "PostgreSQL prevents lost updates."}]
        record.title = "Database durability"

    updated = postgres_store.mutate_conversation(conversation["id"], user["user_id"], add_message)
    assert updated["messages"][0]["content"].startswith("PostgreSQL")
    assert postgres_store.list_conversations(user["user_id"])[0]["title"] == "Database durability"

    assert postgres_store.clear_conversations(user["user_id"]) == 1
    assert postgres_store.delete_user_record(user["user_id"]) is True


def test_conversation_repository_uses_relational_source_of_truth(relational_store, monkeypatch) -> None:
    monkeypatch.setattr(conversation_store, "DATABASE_ENABLED", True)
    user = postgres_store.create_user("conversation.database", "pbkdf2-hash")
    assert user is not None
    user_id = user["user_id"]
    conversation_id = "7ab4ef03-50ba-4782-95db-ecc55d64c53d"

    conversation_store.append_session_message(
        conversation_id, "user", "Persist this message in PostgreSQL", user_id
    )
    conversation_store.append_session_message(
        conversation_id, "assistant", "The database is the source of truth.", user_id
    )
    stored = conversation_store.get_conversation(conversation_id, user_id)

    assert [message["role"] for message in stored["messages"]] == ["user", "assistant"]
    assert stored["title"].startswith("Persist this message")
    assert conversation_store.list_conversations(user_id)[0]["id"] == conversation_id
    assert conversation_store.clear_conversations(user_id) == 1


def test_production_database_requires_alembic_schema(monkeypatch) -> None:
    path = Path(__file__).with_name("_missing_schema_test.db")
    path.unlink(missing_ok=True)
    empty_engine = create_engine(f"sqlite:///{path.as_posix()}")
    monkeypatch.setattr(database, "engine", empty_engine)
    monkeypatch.setattr(database.settings, "ENVIRONMENT", "production")

    try:
        with pytest.raises(RuntimeError, match="alembic upgrade head"):
            database.initialize_database()
        database.Base.metadata.create_all(empty_engine)
        database.initialize_database()
    finally:
        empty_engine.dispose()
        path.unlink(missing_ok=True)
