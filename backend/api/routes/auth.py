from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config.settings import settings
from services.auth import (
    create_access_token,
    create_refresh_token,
    change_password,
    get_username,
    login,
    register,
    user_exists,
    verify_token,
)
from services.refresh_sessions import consume as consume_refresh_session
from services.refresh_sessions import issue as issue_refresh_session
from services.refresh_sessions import revoke as revoke_refresh_session
from services.refresh_sessions import revoke_user as revoke_user_refresh_sessions
from services.user_preferences import load_preferences, save_preferences

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class PreferencesRequest(BaseModel):
    display_name: str = Field(default="", max_length=80)
    theme: Literal["light", "dark", "system"] = "dark"
    language: Literal["auto", "english", "vietnamese"] = "auto"
    character_style: Literal["warm", "enthusiastic", "professional", "concise", "friendly", "custom"] = "professional"
    nickname: str = Field(default="", max_length=80)
    custom_instructions: str = Field(default="", max_length=4000)


class PreferencesPatchRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    theme: Literal["light", "dark", "system"] | None = None
    language: Literal["auto", "english", "vietnamese"] | None = None
    character_style: Literal["warm", "enthusiastic", "professional", "concise", "friendly", "custom"] | None = None
    nickname: str | None = Field(default=None, max_length=80)
    custom_instructions: str | None = Field(default=None, max_length=4000)


def _set_refresh_cookie(response: Response, user_id: str) -> None:
    refresh_token = create_refresh_token(user_id)
    payload = verify_token(refresh_token, expected_type="refresh") or {}
    issue_refresh_session(refresh_token, user_id, float(payload.get("exp", 0)))
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_TTL_SECONDS,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


@router.post("/register")
def register_user(req: RegisterRequest, response: Response):
    result = register(req.username, req.password)
    if not result:
        raise HTTPException(status_code=400, detail="Username already exists or invalid credentials")
    _set_refresh_cookie(response, result["user_id"])
    return result


@router.post("/login")
def login_user(req: LoginRequest, response: Response):
    result = login(req.username, req.password)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    _set_refresh_cookie(response, result["user_id"])
    return result


@router.post("/refresh")
def refresh_session(request: Request, response: Response):
    refresh_token = request.cookies.get(settings.REFRESH_COOKIE_NAME, "")
    payload = verify_token(refresh_token, expected_type="refresh")
    user_id = payload.get("user_id", "") if payload else ""
    if not user_id or not user_exists(user_id):
        failure = JSONResponse(status_code=401, content={"detail": "Session expired"})
        _clear_refresh_cookie(failure)
        return failure
    if not consume_refresh_session(refresh_token, user_id):
        # Do not emit a deletion cookie for a valid-but-already-consumed token.
        # Another tab may just have rotated it and installed the replacement.
        return JSONResponse(
            status_code=401,
            content={"detail": "Session expired"},
            headers={"Cache-Control": "no-store"},
        )
    _set_refresh_cookie(response, user_id)
    return {
        "access_token": create_access_token(user_id),
        "user_id": user_id,
        "username": get_username(user_id),
    }


@router.post("/logout")
def logout_user(request: Request, response: Response):
    revoke_refresh_session(request.cookies.get(settings.REFRESH_COOKIE_NAME, ""))
    _clear_refresh_cookie(response)
    response.headers["Clear-Site-Data"] = '"cache", "cookies"'
    return {"status": "success"}


@router.get("/me")
def get_me(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user_id": user_id, "username": get_username(user_id)}


@router.get("/preferences")
def get_preferences(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    preferences = load_preferences(user_id)
    if not preferences["display_name"]:
        preferences["display_name"] = get_username(user_id) or "User"
    return preferences


@router.put("/preferences")
def update_preferences(request: Request, body: PreferencesRequest):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return save_preferences(user_id, body.model_dump())


@router.patch("/preferences")
def patch_preferences(request: Request, body: PreferencesPatchRequest):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    preferences = load_preferences(user_id)
    preferences.update(body.model_dump(exclude_none=True))
    return save_preferences(user_id, preferences)


@router.post("/change-password")
def update_password(request: Request, response: Response, body: ChangePasswordRequest):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="New password must be different")
    if not change_password(user_id, body.current_password, body.new_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    revoke_user_refresh_sessions(user_id)
    _set_refresh_cookie(response, user_id)
    return {"status": "success", "message": "Password updated"}


@router.get("/export")
def export_account_data(request: Request, response: Response):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from api.routes.documents import _list_upload_files
    from services.conversation_store import list_conversations
    response.headers["Cache-Control"] = "no-store"
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": {"user_id": user_id, "username": get_username(user_id)},
        "preferences": load_preferences(user_id),
        "conversations": list_conversations(user_id),
        "documents": _list_upload_files(user_id),
    }


@router.delete("/account")
def delete_account(request: Request, response: Response):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from services.auth import delete_user
    ok = delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    revoke_refresh_session(request.cookies.get(settings.REFRESH_COOKIE_NAME, ""))
    _clear_refresh_cookie(response)
    return {"status": "success", "message": "Account and all associated data deleted"}
