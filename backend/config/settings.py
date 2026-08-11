import os
from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


class Settings:
    APP_VERSION: str = os.getenv("APP_VERSION", "2.1.0")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").strip().lower()

    # Provider: "ollama" (local) or "groq" (cloud-free, no GPU needed)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq").strip().lower()

    # Ollama
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "qwen3:4b-instruct")

    # Groq (free, no VPS needed)
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    # Optional OpenAI-compatible embedding endpoint. Leave empty for BM25-only
    # retrieval; Groq's chat endpoint is not an embedding service.
    EMBEDDING_BASE_URL: str = os.getenv("EMBEDDING_BASE_URL", "").rstrip("/")
    EMBEDDING_API_KEY: str = os.getenv("EMBEDDING_API_KEY", "")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text-v1.5")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "768"))
    RRF_K: int = int(os.getenv("RRF_K", "60"))
    TOP_K: int = int(os.getenv("TOP_K", "5"))
    BROAD_TOP_K: int = int(os.getenv("BROAD_TOP_K", "20"))
    MIN_SIMILARITY_SCORE: float = float(os.getenv("MIN_SIMILARITY_SCORE", "0.0"))
    RETRIEVAL_CONFIDENCE_THRESHOLD: float = float(os.getenv("RETRIEVAL_CONFIDENCE_THRESHOLD", "0.0"))
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.1"))
    LLM_TOP_K: int = int(os.getenv("LLM_TOP_K", "40"))
    LLM_TOP_P: float = float(os.getenv("LLM_TOP_P", "0.9"))
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "2048"))
    NUM_CTX: int = int(os.getenv("NUM_CTX", "4096"))
    MAX_HISTORY_MESSAGES: int = int(os.getenv("MAX_HISTORY_MESSAGES", "4"))
    MAX_CHUNK_CHARS: int = int(os.getenv("MAX_CHUNK_CHARS", "1000"))
    MAX_CONTEXT_CHARS: int = int(os.getenv("MAX_CONTEXT_CHARS", "6000"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    READINESS_CACHE_SECONDS: float = float(os.getenv("READINESS_CACHE_SECONDS", "10"))
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", "120"))
    RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    AUTH_RATE_LIMIT_REQUESTS: int = int(os.getenv("AUTH_RATE_LIMIT_REQUESTS", "10"))
    UPLOAD_FOLDER: str = os.getenv(
        "UPLOAD_FOLDER",
        str(BACKEND_DIR / "uploads"),
    )
    MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://localhost:5173,"
            "http://127.0.0.1:3000,http://127.0.0.1:5173,"
            "https://novaaiagent.vercel.app",
        ).split(",")
        if origin.strip()
    ]

    # Auth
    JWT_SECRET: str = os.getenv("JWT_SECRET", "nova-ai-default-secret")

    # Backblaze B2 (S3-compatible storage)
    B2_KEY_ID: str = os.getenv("B2_KEY_ID", "")
    B2_APP_KEY: str = os.getenv("B2_APP_KEY", "")
    B2_BUCKET: str = os.getenv("B2_BUCKET", "nova-ai-storage")
    B2_ENDPOINT: str = os.getenv("B2_ENDPOINT", "https://s3.us-west-004.backblazeb2.com")


settings = Settings()

if settings.ENVIRONMENT == "production" and settings.JWT_SECRET == "nova-ai-default-secret":
    raise RuntimeError("JWT_SECRET must be configured in production")
