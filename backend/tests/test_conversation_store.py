from pathlib import Path

import pytest

from services import conversation_store as store


@pytest.fixture
def isolated_store(monkeypatch):
    store_file = Path(__file__).with_name("_conversations_test.json")
    temp_file = store_file.with_suffix(".tmp")
    store_file.unlink(missing_ok=True)
    temp_file.unlink(missing_ok=True)
    monkeypatch.setattr(store, "_store_file_for", lambda _user_id: store_file)
    yield
    store_file.unlink(missing_ok=True)
    temp_file.unlink(missing_ok=True)


def test_conversation_lifecycle(isolated_store) -> None:
    user_id = "portfolio-user"
    conversation = store.create_conversation(
        user_id,
        conversation_id="conversation-1",
        pinned=False,
    )
    assert conversation["title"] == "New Chat"
    assert store.create_conversation(user_id, conversation_id="conversation-1") == conversation

    conversation = store.append_session_message(
        "conversation-1",
        "user",
        "Explain reciprocal rank fusion and why it improves hybrid retrieval",
        user_id,
    )
    assert conversation["title"].endswith("...")

    store.append_session_message(
        "conversation-1",
        "assistant",
        "It combines rankings from multiple retrieval systems.",
        user_id,
    )
    history = store.get_session_history("conversation-1", user_id)
    assert [message["role"] for message in history] == ["user", "assistant"]

    updated = store.update_conversation(
        "conversation-1",
        user_id,
        title="Hybrid retrieval notes",
        pinned=True,
    )
    assert updated["title"] == "Hybrid retrieval notes"
    assert updated["pinned"] is True
    assert store.list_conversations(user_id)[0]["id"] == "conversation-1"

    store.prepare_regeneration("conversation-1", user_id)
    assert [message["role"] for message in store.get_session_history("conversation-1", user_id)] == ["user"]

    store.delete_conversation("conversation-1", user_id)
    assert store.list_conversations(user_id) == []
    with pytest.raises(KeyError):
        store.get_conversation("conversation-1", user_id)


def test_clear_and_missing_conversation_paths(isolated_store) -> None:
    user_id = "portfolio-user"
    store.append_session_message("auto-created", "user", "Short title", user_id)
    assert store.get_conversation("auto-created", user_id)["title"] == "Short title"
    assert store.get_session_history("missing", user_id) == []

    store.prepare_regeneration("missing", user_id)
    assert store.clear_conversations(user_id) == 1
    assert store.clear_conversations(user_id) == 0

    with pytest.raises(KeyError):
        store.delete_conversation("missing", user_id)
    with pytest.raises(KeyError):
        store.update_conversation("missing", user_id, title="Nope")


def test_history_is_normalized_and_limited() -> None:
    messages = [
        {"role": "user", "content": f"message-{index}", "ignored": True}
        for index in range(12)
    ]
    messages.append({"invalid": True})

    history = store._normalize_history(messages)

    assert len(history) == 9
    assert history[0] == {"role": "user", "content": "message-3"}
    assert all(set(message) == {"role", "content"} for message in history)
