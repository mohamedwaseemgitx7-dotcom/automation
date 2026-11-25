"""Database schema (SQLite now, Postgres later via DATABASE_URL)."""
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text,
                        create_engine, select)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import get_settings


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class BotConfig(Base):
    __tablename__ = "bot_config"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_name: Mapped[str] = mapped_column(String(80), default="")
    role: Mapped[str] = mapped_column(String(200), default="")
    business_name: Mapped[str] = mapped_column(String(160), default="")
    business_description: Mapped[str] = mapped_column(Text, default="")
    website: Mapped[str] = mapped_column(String(300), default="")
    objective: Mapped[str] = mapped_column(Text, default="")
    allowed_topics: Mapped[list] = mapped_column(JSON, default=list)
    blocked_topics: Mapped[list] = mapped_column(JSON, default=list)
    languages: Mapped[list] = mapped_column(JSON, default=list)
    tone: Mapped[str] = mapped_column(String(60), default="friendly and professional")
    max_words: Mapped[int] = mapped_column(Integer, default=90)
    handoff_message: Mapped[str] = mapped_column(
        Text, default="I don't have verified information about this. Let me connect you with the business owner.")
    instructions: Mapped[str] = mapped_column(Text, default="")
    image_understanding: Mapped[bool] = mapped_column(Boolean, default=False)
    voice_understanding: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zip_name: Mapped[str] = mapped_column(String(255))
    zip_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="processing")  # processing|ready|failed
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class KnowledgeFile(Base):
    __tablename__ = "knowledge_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(20))   # document|image|audio|skipped
    size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # ok|failed|skipped
    chunks: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(String(300), default="")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("knowledge_files.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(500))
    location: Mapped[str] = mapped_column(String(60), default="")   # page / sheet / section
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)       # float32 vector


class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(80))
    wa_id: Mapped[str] = mapped_column(String(32), unique=True)
    automation: Mapped[bool] = mapped_column(Boolean, default=True)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), unique=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True)   # duplicate guard
    jid: Mapped[str | None] = mapped_column(String(80))                           # reply address
    direction: Mapped[str] = mapped_column(String(3))  # in|out
    msg_type: Mapped[str] = mapped_column(String(20), default="text")
    text: Mapped[str | None] = mapped_column(Text)
    normalised: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(8))
    decision: Mapped[str | None] = mapped_column(String(40))
    sources: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="received")
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class WaSession(Base):
    __tablename__ = "wa_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    adapter: Mapped[str] = mapped_column(String(20), default="baileys")
    status: Mapped[str] = mapped_column(String(20), default="disconnected")
    account: Mapped[str] = mapped_column(String(80), default="")      # masked number only
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class WaConsent(Base):
    __tablename__ = "wa_consent"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    text: Mapped[str] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    actor: Mapped[str] = mapped_column(String(20))   # owner|ai|system
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class ReadinessRun(Base):
    __tablename__ = "readiness_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ready: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[float] = mapped_column(Float, default=0)
    report: Mapped[dict] = mapped_column(JSON, default=dict)


_Session: sessionmaker | None = None


def init(url: str | None = None) -> sessionmaker:
    global _Session
    url = url or get_settings().database_url
    eng = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
                        pool_pre_ping=True)
    Base.metadata.create_all(eng)
    _add_missing_columns(eng)
    _Session = sessionmaker(eng, expire_on_commit=False)
    purge_oversized()
    return _Session


def _add_missing_columns(eng) -> None:
    """Tiny forward-only migration: add new nullable columns to existing tables."""
    from sqlalchemy import inspect, text as sql
    insp = inspect(eng)
    with eng.begin() as con:
        for table in Base.metadata.sorted_tables:
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in have and col.nullable:
                    con.execute(sql(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(eng.dialect)}'))


MAX_TEXT_CHARS = 4000


def purge_oversized() -> int:
    """Safety net: delete any message row whose stored text is larger than a normal chat message."""
    from sqlalchemy import delete as sql_delete, func as sql_func
    with session() as s:
        n = s.execute(sql_delete(Message).where(sql_func.length(Message.text) > MAX_TEXT_CHARS)).rowcount or 0
        if n:
            s.add(AuditLog(actor="system", action="oversized_messages_deleted", detail={"rows": n}))
        s.commit()
        return n


def session() -> Session:
    if _Session is None:
        init()
    return _Session()


def get_config(s: Session) -> BotConfig:
    cfg = s.scalar(select(BotConfig).limit(1))
    if cfg is None:
        cfg = BotConfig()
        s.add(cfg)
        s.flush()
    return cfg


def audit(s: Session, actor: str, action: str, **detail) -> None:
    s.add(AuditLog(actor=actor, action=action, detail=detail))
