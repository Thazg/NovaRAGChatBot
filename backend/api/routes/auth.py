from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config.settings import settings
from services.auth import (
    create_access_token,
    create_refresh_token,
    get_username,
    login,
    register,
    user_exists,
    verify_token,
)
from services.refresh_sessions import consume as consume_refresh_session
from services.refresh_sessions import issue as issue_refresh_session
from services.refresh_sessions import revoke as revoke_refresh_session

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=1, max_length=256)


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
    return {"user_id": user_id}


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
