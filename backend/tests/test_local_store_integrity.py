import pytest

from services import auth, conversation_store


@pytest.mark.parametrize("payload", ['{"truncated":', '[]'])
def test_register_does_not_replace_an_unreadable_user_database(tmp_path, monkeypatch, payload):
    path = tmp_path / "users.json"
    path.write_text(payload)
    monkeypatch.setattr(auth, "USERS_FILE", path)
    monkeypatch.setattr(auth, "DATABASE_ENABLED", False)
    with pytest.raises(RuntimeError, match="User store is unreadable"):
        auth.register("new.user", "strong-password")
    assert path.read_text() == payload


@pytest.mark.parametrize("payload", ['{"truncated":', '[]'])
def test_append_does_not_replace_an_unreadable_conversation_store(tmp_path, monkeypatch, payload):
    path = tmp_path / "conversations.json"
    path.write_text(payload)
    monkeypatch.setattr(conversation_store, "_store_file_for", lambda user: path)
    monkeypatch.setattr(conversation_store, "DATABASE_ENABLED", False)
    with pytest.raises(RuntimeError, match="Conversation store is unreadable"):
        conversation_store.append_session_message("session", "user", "new message", "integrity-owner")
    assert path.read_text() == payload
