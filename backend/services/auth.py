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

BACKEND_DIR = Path(__file__).resolve().parents[1]
USERS_FILE = BACKEND_DIR / "storage" / "users.json"
USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
JWT_SECRET = settings.JWT_SECRET or "nova-ai-default-secret"
JWT_EXPIRY = 86400 * 30
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


def create_token(user_id: str) -> str:
    import json
    header = _base64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _base64url_encode(json.dumps({
        "user_id": user_id,
        "exp": int(time.time()) + JWT_EXPIRY,
    }).encode())
    signing_input = f"{header}.{payload}"
    sig = _base64url_encode(hmac.new(
        JWT_SECRET.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
    ).digest())
    return f"{header}.{payload}.{sig}"


def verify_token(token: str) -> dict | None:
    import json
    parts = token.split(".")
    if len(parts) != 3:
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
        if header_data.get("alg") != "HS256" or header_data.get("typ") != "JWT":
            return None
        data = json.loads(_base64url_decode(payload))
    except Exception:
        return None
    if data.get("exp", 0) < time.time():
        return None
    try:
        uuid.UUID(str(data.get("user_id", "")))
    except (ValueError, TypeError, AttributeError):
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
            with USERS_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_users(users: dict) -> None:
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
    with _USERS_LOCK:
        return any(
            isinstance(user, dict) and user.get("user_id") == user_id
            for user in _load_users().values()
        )


def delete_user(user_id: str) -> bool:
    with _USERS_LOCK:
        users = _load_users()
        username_to_delete = None
        for uname, data in list(users.items()):
            if data.get("user_id") == user_id:
                username_to_delete = uname
                break
        if not username_to_delete:
            return False
        del users[username_to_delete]
        _save_users(users)

    # Clean up local user data.
    upload_dir = Path(settings.UPLOAD_FOLDER) / user_id
    if upload_dir.exists():
        shutil.rmtree(upload_dir, ignore_errors=True)

    # Remove vector store
    from rag.vector_store import BASE_INDEX_DIR
    index_dir = BASE_INDEX_DIR / user_id
    if index_dir.exists():
        shutil.rmtree(index_dir, ignore_errors=True)

    # Remove conversations
    conv_file = BACKEND_DIR / "storage" / "sessions" / user_id / "conversations.json"
    if conv_file.exists():
        conv_file.unlink(missing_ok=True)

    # Remove matching remote objects when B2 is configured.
    try:
        from services.remote_storage import delete_file, list_files
        for prefix in (f"uploads/{user_id}/", f"index/{user_id}/", f"sessions/{user_id}/"):
            for remote_path in list_files(prefix):
                delete_file(remote_path)
    except Exception:
        pass

    try:
        from rag.rag_chain import unload_vector_store
        unload_vector_store(user_id)
    except Exception:
        pass

    return True


def register(username: str, password: str) -> dict | None:
    username = username.strip().lower()
    if not USERNAME_PATTERN.fullmatch(username):
        return None
    if len(password) < 8 or len(password) > 256:
        return None
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
    token = create_token(user_id)
    return {"token": token, "user_id": user_id, "username": username}


def login(username: str, password: str) -> dict | None:
    username = username.strip().lower()
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
    token = create_token(user["user_id"])
    return {"token": token, "user_id": user["user_id"], "username": username}
