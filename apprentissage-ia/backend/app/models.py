from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite drops tzinfo, so we keep everything naive)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(2))
    language: Mapped[str] = mapped_column(String(5), default="fr")
    establishment: Mapped[str | None] = mapped_column(String(200))
    level: Mapped[str | None] = mapped_column(String(100))
    filiere: Mapped[str | None] = mapped_column(String(100))
    specialite: Mapped[str | None] = mapped_column(String(100))
    academic_year: Mapped[str | None] = mapped_column(String(20))

    plan: Mapped[str] = mapped_column(String(20), default="free")
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    ai_credits: Mapped[int] = mapped_column(Integer, default=0)

    xp: Mapped[int] = mapped_column(Integer, default=0)
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_active_date: Mapped[date | None] = mapped_column(Date)

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    semester: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="subject", cascade="all, delete-orphan", order_by="Chapter.position"
    )


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer, default=0)
    notions: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    subject: Mapped[Subject] = relationship(back_populates="chapters")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"))
    filename: Mapped[str] = mapped_column(String(255))
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    chunks: Mapped[list[DocumentChunk]] = relationship(
        cascade="all, delete-orphan", order_by="DocumentChunk.position"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (Index("ix_chunks_user_subject", "user_id", "subject_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    subject_id: Mapped[int] = mapped_column(Integer)
    chapter_id: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class Exercise(Base):
    """A QCM question. owner_id None = shared bank question (validated by the team)."""

    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    choices: Mapped[list[str]] = mapped_column(JSON)
    answer_index: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(20), default="moyen")
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class QuizSession(Base):
    __tablename__ = "quiz_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # quiz | evaluation
    subject_id: Mapped[int | None] = mapped_column(Integer)
    chapter_id: Mapped[int | None] = mapped_column(Integer)
    exercise_ids: Mapped[list[int]] = mapped_column(JSON)
    total: Mapped[int] = mapped_column(Integer)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | submitted
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (Index("ix_attempts_user_exercise", "user_id", "exercise_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"))
    session_id: Mapped[int | None] = mapped_column(ForeignKey("quiz_sessions.id", ondelete="SET NULL"))
    chosen_index: Mapped[int | None] = mapped_column(Integer)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(20))  # quiz | evaluation | review
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReviewItem(Base):
    """Spaced-repetition state for one question (SM-2 style)."""

    __tablename__ = "review_items"
    __table_args__ = (UniqueConstraint("user_id", "exercise_id", name="uq_review_user_exercise"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"))
    ease: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PromoCode(Base):
    __tablename__ = "promo_codes"

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    percent_off: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    max_uses: Mapped[int | None] = mapped_column(Integer)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tx_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    product: Mapped[str] = mapped_column(String(40))
    amount: Mapped[int] = mapped_column(Integer)  # amount to be paid, after discount
    discount: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3))
    country: Mapped[str] = mapped_column(String(2))
    provider: Mapped[str] = mapped_column(String(40))
    provider_tx_id: Mapped[str | None] = mapped_column(String(100))
    promo_code: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | succeeded | failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)


class AIUsage(Base):
    """One row per AI call. Serves both quota enforcement and cost accounting."""

    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30))  # explain | generate_qcm | analyze_document
    model: Mapped[str] = mapped_column(String(60), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    paid_with: Mapped[str] = mapped_column(String(10))  # quota | credits
    status: Mapped[str] = mapped_column(String(10), default="reserved")  # reserved | done | failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AICache(Base):
    __tablename__ = "ai_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
