import hashlib
import hmac
import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from config.settings import settings
from services.database import DATABASE_ENABLED

BACKEND_DIR = Path(__file__).resolve().parents[1]
USERS_FILE = BACKEND_DIR / "storage" / "users.json"
USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
JWT_SECRET = settings.JWT_SECRET or "nova-ai-default-secret"
PASSWORD_ITERATIONS = 310_000
USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]{2,40}$")
_USERS_LOCK = threading.RLock()


def _base64url_encode(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _base64url_decode(s: str) -> bytes:
    import base64
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored_hash: str) -> tuple[bool, bool]:
    """Return (valid, needs_migration), supporting legacy SHA-256 records."""
    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt_hex, digest_hex = stored_hash.split("$", 3)
            candidate = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                bytes.fromhex(salt_hex),
                int(iterations),
            ).hex()
            return hmac.compare_digest(candidate, digest_hex), False
        except (TypeError, ValueError):
            return False, False

    legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
    valid = hmac.compare_digest(legacy, stored_hash)
    return valid, valid


def _create_token(user_id: str, token_type: str, expires_in: int) -> str:
    import json
    header = _base64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _base64url_encode(json.dumps({
        "user_id": user_id,
        "type": token_type,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in,
        "jti": uuid.uuid4().hex,
    }).encode())
    signing_input = f"{header}.{payload}"
    sig = _base64url_encode(hmac.new(
        JWT_SECRET.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
    ).digest())
    return f"{header}.{payload}.{sig}"


def create_access_token(user_id: str) -> str:
    return _create_token(user_id, "access", settings.ACCESS_TOKEN_TTL_SECONDS)


def create_refresh_token(user_id: str) -> str:
    return _create_token(user_id, "refresh", settings.REFRESH_TOKEN_TTL_SECONDS)


def create_token(user_id: str) -> str:
    """Backward-compatible alias for short-lived access tokens."""
    return create_access_token(user_id)


def verify_token(token: str, expected_type: str = "access") -> dict | None:
    import math
    # Validate the entire untrusted envelope before ASCII encoding/HMAC. A bad
    # Authorization header must be an authentication failure, never a 500.
    if not isinstance(token, str) or len(token) > 8192:
        return None
    parts = token.split(".")
    if len(parts) != 3 or any(not re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in parts):
        return None
    header, payload, sig = parts
    signing_input = f"{header}.{payload}"
    expected = _base64url_encode(hmac.new(
        JWT_SECRET.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
    ).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        header_data = json.loads(_base64url_decode(header))
        data = json.loads(_base64url_decode(payload))
        if not isinstance(header_data, dict) or not isinstance(data, dict):
            return None
        if header_data.get("alg") != "HS256" or header_data.get("typ") != "JWT":
            return None
        expires = data.get("exp")
        if isinstance(expires, bool) or not isinstance(expires, (int, float)) or not math.isfinite(expires):
            return None
        if expires <= time.time() or data.get("type") != expected_type:
            return None
        uuid.UUID(str(data.get("user_id", "")))
    except (ValueError, TypeError, OverflowError, UnicodeError):
        return None
    return data


def _load_users() -> dict:
    if not USERS_FILE.exists():
        try:
            from services.remote_storage import download_file
            download_file("data/users.json", USERS_FILE)
        except Exception:
            pass
    if USERS_FILE.exists():
        try:
            payload = json.loads(USERS_FILE.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Expected a user mapping")
            return payload
        except (OSError, ValueError) as exc:
            raise RuntimeError("User store is unreadable; restore or repair it before accepting writes") from exc
    return {}


def _save_users(users: dict, *, required: bool = False) -> None:
    if required:
        from services.remote_storage import upload_bytes
        if not upload_bytes("data/users.json", json.dumps(users, ensure_ascii=False).encode()):
            raise RuntimeError("Could not persist account removal")
    temp_file = USERS_FILE.with_suffix(".tmp")
    with temp_file.open("w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    os.replace(temp_file, USERS_FILE)
    try:
        from services.remote_storage import upload_file
        upload_file("data/users.json", USERS_FILE)
    except Exception:
        pass


def user_exists(user_id: str) -> bool:
    if DATABASE_ENABLED:
        from services.postgres_store import find_user_by_id
        return find_user_by_id(user_id) is not None
    with _USERS_LOCK:
        return any(
            isinstance(user, dict) and user.get("user_id") == user_id
            for user in _load_users().values()
        )


def get_username(user_id: str) -> str | None:
    if DATABASE_ENABLED:
        from services.postgres_store import find_user_by_id
        user = find_user_by_id(user_id)
        return user.get("username") if user else None
    with _USERS_LOCK:
        for username, user in _load_users().items():
            if isinstance(user, dict) and user.get("user_id") == user_id:
                return username
    return None


def change_password(user_id: str, current_password: str, new_password: str) -> bool:
    if len(new_password) < 8 or len(new_password) > 256:
        return False
    if DATABASE_ENABLED:
        from services.postgres_store import find_user_by_id, update_password
        user = find_user_by_id(user_id)
        if not user or not _verify_password(current_password, user.get("password_hash", ""))[0]:
            return False
        update_password(user_id, _hash_password(new_password))
        return True
    with _USERS_LOCK:
        users = _load_users()
        for user in users.values():
            if isinstance(user, dict) and user.get("user_id") == user_id:
                if not _verify_password(current_password, user.get("password_hash", ""))[0]:
                    return False
                user["password_hash"] = _hash_password(new_password)
                _save_users(users)
                return True
    return False


def delete_user(user_id: str) -> bool:
    from services.index_jobs import _user_index_lock
    from services.account_lifecycle import mark_deleting
    from services import conversation_store, user_preferences, refresh_sessions
    from rag import vector_store, rag_chain
    from services.remote_storage import delete_file, list_files

    with _user_index_lock(user_id):
        if not user_exists(user_id):
            return False
        # Keep credentials until cleanup succeeds so failures remain retryable.
        mark_deleting(user_id)
        refresh_sessions.revoke_user(user_id)
        remote_required = vector_store._remote_enabled()
        for prefix in (f"uploads/{user_id}/", f"index/{user_id}/", f"sessions/{user_id}/"):
            paths = list_files(prefix, required=True) if remote_required else list_files(prefix)
            for remote_path in paths:
                if not delete_file(remote_path) and remote_required:
                    raise RuntimeError("Could not finish remote account cleanup")
        if remote_required and not delete_file(f"preferences/{user_id}.json"):
            raise RuntimeError("Could not remove remote preferences")
        # Writers hold this same user lock, so neither delayed streams nor jobs
        # can recreate these artifacts after the barrier is installed.
        from api.routes.documents import BASE_UPLOADS_DIR
        for path in (BASE_UPLOADS_DIR / user_id, vector_store.BASE_INDEX_DIR / user_id,
                     conversation_store.BASE_DIR / user_id):
            if path.exists():
                shutil.rmtree(path)
        preference_path = user_preferences.BASE_DIR / f"{user_id}.json"
        preference_path.unlink(missing_ok=True)
        rag_chain.unload_vector_store(user_id)
        if DATABASE_ENABLED:
            from services.postgres_store import delete_user_record
            return delete_user_record(user_id)
        with _USERS_LOCK:
            users = _load_users()
            for username, record in list(users.items()):
                if isinstance(record, dict) and record.get("user_id") == user_id:
                    del users[username]
                    _save_users(users, required=remote_required)
                    return True
        return False


def register(username: str, password: str) -> dict | None:
    username = username.strip().lower()
    if not USERNAME_PATTERN.fullmatch(username):
        return None
    if len(password) < 8 or len(password) > 256:
        return None
    if DATABASE_ENABLED:
        from services.postgres_store import create_user
        user = create_user(username, _hash_password(password))
        if not user:
            return None
        user_id = user["user_id"]
    else:
        with _USERS_LOCK:
            users = _load_users()
            if username in users:
                return None
            user_id = str(uuid.uuid4())
            users[username] = {
                "user_id": user_id,
                "password_hash": _hash_password(password),
                "created_at": time.time(),
            }
            _save_users(users)
    token = create_access_token(user_id)
    return {"access_token": token, "user_id": user_id, "username": username}


def login(username: str, password: str) -> dict | None:
    username = username.strip().lower()
    if DATABASE_ENABLED:
        from services.postgres_store import find_user_by_username, update_password
        user = find_user_by_username(username)
        if not user:
            return None
        valid, needs_migration = _verify_password(password, user.get("password_hash", ""))
        if not valid:
            return None
        if needs_migration:
            update_password(user["user_id"], _hash_password(password))
    else:
        with _USERS_LOCK:
            users = _load_users()
            user = users.get(username)
            if not user:
                return None
            valid, needs_migration = _verify_password(password, user.get("password_hash", ""))
            if not valid:
                return None
            if needs_migration:
                user["password_hash"] = _hash_password(password)
                _save_users(users)
    token = create_access_token(user["user_id"])
    return {"access_token": token, "user_id": user["user_id"], "username": username}
