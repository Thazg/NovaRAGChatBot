from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from api.routes import auth, chat, health, conversation, documents
from config.settings import settings
from services.auth import user_exists, verify_token
from services.rate_limiter import create_rate_limiter
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Initializing Nova AI Agent Backend...")
    from services.database import initialize_database
    initialize_database()
    Path(settings.UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
    logger.info("Upload folder ready at %s", settings.UPLOAD_FOLDER)
    from rag.llm_client import warmup_model
    await warmup_model()
    yield


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.user_id = None
        path = request.url.path
        if request.method == "OPTIONS" or path.startswith("/health") or path in (
            "/auth/register", "/auth/login", "/auth/refresh", "/auth/logout"
        ):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            payload = verify_token(auth_header[7:])
            if payload and user_exists(payload.get("user_id", "")):
                request.state.user_id = payload.get("user_id")

        if not request.state.user_id:
            return JSONResponse(status_code=401, content={"detail": "Authentication required"})

        return await call_next(request)


class TrustedOriginMiddleware(BaseHTTPMiddleware):
    """Protect cookie-backed auth endpoints from cross-site request forgery."""

    _COOKIE_ENDPOINTS = {"/auth/register", "/auth/login", "/auth/refresh", "/auth/logout"}

    async def dispatch(self, request: Request, call_next):
        if request.method == "POST" and request.url.path in self._COOKIE_ENDPOINTS:
            origin = request.headers.get("Origin", "").rstrip("/")
            exact_match = origin in settings.CORS_ORIGINS
            regex_match = bool(
                origin
                and settings.CORS_ORIGIN_REGEX
                and re.fullmatch(settings.CORS_ORIGIN_REGEX, origin)
            )
            if (origin and not (exact_match or regex_match)) or (
                settings.ENVIRONMENT == "production" and not origin
            ):
                return JSONResponse(status_code=403, content={"detail": "Untrusted request origin"})
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.general = create_rate_limiter(
            settings.RATE_LIMIT_REQUESTS,
            settings.RATE_LIMIT_WINDOW_SECONDS,
            "api",
        )
        self.auth = create_rate_limiter(
            settings.AUTH_RATE_LIMIT_REQUESTS,
            settings.RATE_LIMIT_WINDOW_SECONDS,
            "auth",
        )

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            not settings.RATE_LIMIT_ENABLED
            or request.method == "OPTIONS"
            or path.startswith("/health")
        ):
            return await call_next(request)

        is_auth = path in ("/auth/register", "/auth/login")
        limiter = self.auth if is_auth else self.general
        client_host = request.client.host if request.client else "unknown"
        decision = limiter.check(f"{'auth' if is_auth else 'api'}:{client_host}")
        headers = {
            "X-RateLimit-Limit": str(decision.limit),
            "X-RateLimit-Remaining": str(decision.remaining),
        }
        if not decision.allowed:
            headers["Retry-After"] = str(decision.retry_after)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again shortly."},
                headers=headers,
            )

        response = await call_next(request)
        response.headers.update(headers)
        return response


app = FastAPI(
    title="Nova AI Agent API",
    version=settings.APP_VERSION,
    description="Enterprise RAG backend for Nova AI Agent",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)
app.add_middleware(TrustedOriginMiddleware)
app.add_middleware(RateLimitMiddleware)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """Attach a correlation ID and server timing to every response."""
    request_id = request.headers.get("X-Request-ID", "").strip()[:128] or uuid.uuid4().hex
    request.state.request_id = request_id
    started_at = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - started_at) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
    response.headers["Server-Timing"] = f"app;dur={duration_ms:.2f}"
    logger.info(
        "%s %s -> %s in %.2fms request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error("Global exception request_id=%s: %s", request_id, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id}
    )

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(conversation.router, prefix="/conversation", tags=["Conversation"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
