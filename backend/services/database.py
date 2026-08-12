from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, String, create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from config.settings import settings


class Base(DeclarativeBase):
    pass


class UserRecord(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)


class RefreshSessionRecord(Base):
    __tablename__ = "refresh_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[float] = mapped_column(Float, index=True, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)


class ConversationRecord(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    messages: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, index=True, nullable=False)

    __table_args__ = (Index("ix_conversations_user_updated", "user_id", "updated_at"),)


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_ENABLED = bool(settings.DATABASE_URL)
engine = None
if DATABASE_ENABLED:
    database_url = _normalize_database_url(settings.DATABASE_URL)
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


def initialize_database() -> None:
    if engine is None:
        return
    if settings.ENVIRONMENT != "production":
        Base.metadata.create_all(engine)
        return
    required_tables = {"users", "refresh_sessions", "conversations"}
    existing_tables = set(inspect(engine).get_table_names())
    missing_tables = required_tables - existing_tables
    if missing_tables:
        raise RuntimeError(
            "Database schema is missing migrations for: "
            f"{', '.join(sorted(missing_tables))}. Run 'alembic upgrade head'."
        )


@contextmanager
def database_session() -> Iterator[Session]:
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured")
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
