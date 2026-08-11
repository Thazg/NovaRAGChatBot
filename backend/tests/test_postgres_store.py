from pathlib import Path

import pytest
from sqlalchemy import create_engine

from services import database, postgres_store


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
