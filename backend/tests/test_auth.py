import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from services import auth, refresh_sessions, user_preferences
from app import app


@pytest.fixture
def isolated_users(monkeypatch):
    users_file = Path(__file__).with_name("_users_test.json")
    refresh_file = Path(__file__).with_name("_refresh_sessions_test.json")
    temp_file = users_file.with_suffix(".tmp")
    refresh_temp_file = refresh_file.with_suffix(".tmp")
    users_file.unlink(missing_ok=True)
    temp_file.unlink(missing_ok=True)
    refresh_file.unlink(missing_ok=True)
    refresh_temp_file.unlink(missing_ok=True)
    monkeypatch.setattr(auth, "USERS_FILE", users_file)
    monkeypatch.setattr(refresh_sessions, "_STORE", refresh_file)
    monkeypatch.setattr(user_preferences, "BASE_DIR", Path(__file__).with_name("_preferences_test"))
    remote_storage = ModuleType("services.remote_storage")
    remote_storage.download_file = lambda *_args, **_kwargs: False
    remote_storage.upload_file = lambda *_args, **_kwargs: False
    monkeypatch.setitem(sys.modules, "services.remote_storage", remote_storage)
    yield
    users_file.unlink(missing_ok=True)
    temp_file.unlink(missing_ok=True)
    refresh_file.unlink(missing_ok=True)
    refresh_temp_file.unlink(missing_ok=True)
    import shutil
    shutil.rmtree(user_preferences.BASE_DIR, ignore_errors=True)


def test_register_login_and_verify_token(isolated_users) -> None:
    registered = auth.register("Portfolio.User", "strong-password")

    assert registered is not None
    assert auth.verify_token(registered["access_token"])["user_id"] == registered["user_id"]
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

    token = result["access_token"]
    replacement = "a" if token[-1] != "a" else "b"

    assert auth.verify_token(token[:-1] + replacement) is None


def test_registration_rejects_unsafe_username(isolated_users) -> None:
    assert auth.register("../admin", "strong-password") is None


def test_refresh_cookie_rotates_without_exposing_refresh_token(isolated_users) -> None:
    client = TestClient(app)
    registered = client.post(
        "/auth/register",
        json={"username": "cookie.user", "password": "strong-password"},
        headers={"Origin": "http://127.0.0.1:5173"},
    )

    assert registered.status_code == 200
    assert "refresh" not in registered.json()
    assert registered.json()["access_token"]
    cookie = registered.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie

    refreshed = client.post(
        "/auth/refresh",
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != registered.json()["access_token"]
    assert "httponly" in refreshed.headers["set-cookie"].lower()


def test_consumed_refresh_token_cannot_be_replayed_or_delete_new_cookie(isolated_users) -> None:
    client = TestClient(app)
    registered = client.post(
        "/auth/register",
        json={"username": "rotation.user", "password": "strong-password"},
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    old_refresh = registered.cookies.get("nova_refresh")
    assert old_refresh

    rotated = client.post(
        "/auth/refresh",
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    assert rotated.status_code == 200
    assert rotated.cookies.get("nova_refresh") != old_refresh

    replay_client = TestClient(app)
    replay_client.cookies.set("nova_refresh", old_refresh)
    replay = replay_client.post(
        "/auth/refresh",
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    assert replay.status_code == 401
    assert "set-cookie" not in replay.headers
    assert replay.headers["cache-control"] == "no-store"


def test_logout_revokes_refresh_session_and_clears_cookie(isolated_users) -> None:
    client = TestClient(app)
    client.post(
        "/auth/register",
        json={"username": "logout.user", "password": "strong-password"},
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    refresh_token = client.cookies.get("nova_refresh")
    assert refresh_token

    logged_out = client.post(
        "/auth/logout",
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    assert logged_out.status_code == 200
    assert "nova_refresh=\"\"" in logged_out.headers["set-cookie"]
    assert logged_out.headers["clear-site-data"] == '"cache", "cookies"'

    replay_client = TestClient(app)
    replay_client.cookies.set("nova_refresh", refresh_token)
    replay = replay_client.post(
        "/auth/refresh",
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    assert replay.status_code == 401


def test_production_cookie_uses_host_prefix_secure_and_strict(isolated_users, monkeypatch) -> None:
    monkeypatch.setattr(auth.settings, "COOKIE_SECURE", True)
    monkeypatch.setattr(auth.settings, "REFRESH_COOKIE_NAME", "__Host-nova_refresh")
    monkeypatch.setattr(auth.settings, "REFRESH_COOKIE_SAMESITE", "strict")
    client = TestClient(app, base_url="https://testserver")

    response = client.post(
        "/auth/register",
        json={"username": "secure.user", "password": "strong-password"},
        headers={"Origin": "https://novachatbot.vercel.app"},
    )

    cookie = response.headers["set-cookie"].lower()
    assert response.status_code == 200
    assert "__host-nova_refresh=" in cookie
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=strict" in cookie
    assert "path=/" in cookie
    assert "domain=" not in cookie


def test_account_preferences_persist_and_export(isolated_users) -> None:
    client = TestClient(app)
    registered = client.post(
        "/auth/register",
        json={"username": "settings.user", "password": "strong-password"},
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    preferences = {
        "display_name": "Nova Researcher",
        "theme": "system",
        "language": "vietnamese",
        "character_style": "concise",
        "nickname": "Thazg",
        "custom_instructions": "Always cite the source document.",
    }

    saved = client.put("/auth/preferences", headers=headers, json=preferences)
    patched = client.patch("/auth/preferences", headers=headers, json={"theme": "light"})
    loaded = client.get("/auth/preferences", headers=headers)
    exported = client.get("/auth/export", headers=headers)

    assert saved.status_code == 200
    assert patched.status_code == 200
    assert patched.json()["theme"] == "light"
    assert patched.json()["language"] == "vietnamese"
    assert loaded.json() == {**preferences, "theme": "light"}
    assert exported.status_code == 200
    assert exported.headers["cache-control"] == "no-store"
    assert exported.json()["account"]["username"] == "settings.user"
    assert exported.json()["preferences"] == {**preferences, "theme": "light"}
    assert exported.json()["conversations"] == []


def test_change_password_verifies_current_password_and_rotates_session(isolated_users) -> None:
    client = TestClient(app)
    registered = client.post(
        "/auth/register",
        json={"username": "password.user", "password": "strong-password"},
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    rejected = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": "wrong-password", "new_password": "new-strong-password"},
    )
    changed = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": "strong-password", "new_password": "new-strong-password"},
    )

    assert rejected.status_code == 400
    assert changed.status_code == 200
    assert "httponly" in changed.headers["set-cookie"].lower()
    assert auth.login("password.user", "strong-password") is None
    assert auth.login("password.user", "new-strong-password") is not None
