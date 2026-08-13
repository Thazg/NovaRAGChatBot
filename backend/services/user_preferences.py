import json
import os
import threading
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1] / "storage" / "preferences"
_LOCK = threading.RLock()

DEFAULT_PREFERENCES = {
    "display_name": "",
    "theme": "dark",
    "language": "auto",
    "character_style": "professional",
    "nickname": "",
    "custom_instructions": "",
}


def _file_for(user_id: str) -> Path:
    path = BASE_DIR / f"{user_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _remote_path(user_id: str) -> str:
    return f"preferences/{user_id}.json"


def load_preferences(user_id: str) -> dict[str, str]:
    path = _file_for(user_id)
    if not path.exists():
        try:
            from services.remote_storage import download_file
            download_file(_remote_path(user_id), path)
        except Exception:
            pass
    payload: dict = {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {
        key: str(payload.get(key, default))
        for key, default in DEFAULT_PREFERENCES.items()
    }


def save_preferences(user_id: str, preferences: dict[str, str]) -> dict[str, str]:
    payload = {
        key: str(preferences.get(key, default))
        for key, default in DEFAULT_PREFERENCES.items()
    }
    path = _file_for(user_id)
    with _LOCK:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
        try:
            from services.remote_storage import upload_file
            upload_file(_remote_path(user_id), path)
        except Exception:
            pass
    return payload


def delete_preferences(user_id: str) -> None:
    _file_for(user_id).unlink(missing_ok=True)
    try:
        from services.remote_storage import delete_file
        delete_file(_remote_path(user_id))
    except Exception:
        pass
