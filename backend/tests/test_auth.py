import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from services import auth


@pytest.fixture
def isolated_users(monkeypatch):
    users_file = Path(__file__).with_name("_users_test.json")
    temp_file = users_file.with_suffix(".tmp")
    users_file.unlink(missing_ok=True)
    temp_file.unlink(missing_ok=True)
    monkeypatch.setattr(auth, "USERS_FILE", users_file)
    remote_storage = ModuleType("services.remote_storage")
    remote_storage.download_file = lambda *_args, **_kwargs: False
    remote_storage.upload_file = lambda *_args, **_kwargs: False
    monkeypatch.setitem(sys.modules, "services.remote_storage", remote_storage)
    yield
    users_file.unlink(missing_ok=True)
    temp_file.unlink(missing_ok=True)


def test_register_login_and_verify_token(isolated_users) -> None:
    registered = auth.register("Portfolio.User", "strong-password")

    assert registered is not None
    assert auth.verify_token(registered["token"])["user_id"] == registered["user_id"]
    stored = json.loads(auth.USERS_FILE.read_text(encoding="utf-8"))
    assert stored["portfolio.user"]["password_hash"].startswith("pbkdf2_sha256$")
    assert "strong-password" not in auth.USERS_FILE.read_text(encoding="utf-8")

    logged_in = auth.login("portfolio.user", "strong-password")
    assert logged_in is not None
    assert logged_in["user_id"] == registered["user_id"]
    assert auth.login("portfolio.user", "wrong-password") is None


def test_token_tampering_is_rejected(isolated_users) -> None:
    result = auth.register("token.user", "strong-password")
    assert result is not None

    token = result["token"]
    replacement = "a" if token[-1] != "a" else "b"

    assert auth.verify_token(token[:-1] + replacement) is None


def test_registration_rejects_unsafe_username(isolated_users) -> None:
    assert auth.register("../admin", "strong-password") is None
