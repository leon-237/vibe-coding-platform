"""AI quota, credits and spend cap.

Flow for every paid AI call:
  1. reserve_ai_op()  -> checks daily quota, else consumes a credit, else refuses
  2. the provider call happens
  3. settle_ai_op()   -> stores tokens and cost; a failed call is refunded
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .catalog import PLAN_LIMITS
from .config import get_settings
from .models import AIUsage, User, utcnow


class QuotaExceeded(Exception):
    """User has no quota or credits left."""


class SpendCapReached(Exception):
    """Global daily AI spend cap reached: service paused for the day."""


def effective_plan(user: User, now: datetime | None = None) -> str:
    now = now or utcnow()
    if user.plan != "free" and user.plan_expires_at and user.plan_expires_at > now:
        return user.plan
    return "free"


def plan_limit(user: User, key: str, now: datetime | None = None) -> object:
    return PLAN_LIMITS[effective_plan(user, now)][key]


def _start_of_day(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _cost_usd(input_tokens: int, output_tokens: int) -> float:
    settings = get_settings()
    return (
        input_tokens * settings.ai_input_usd_per_mtok + output_tokens * settings.ai_output_usd_per_mtok
    ) / 1_000_000


def reserve_ai_op(db: Session, user: User, kind: str) -> AIUsage:
    now = utcnow()
    today = _start_of_day(now)

    spent_today = db.scalar(
        select(func.sum(AIUsage.cost_usd)).where(AIUsage.created_at >= today, AIUsage.status == "done")
    ) or 0.0
    if spent_today >= get_settings().daily_ai_spend_cap_usd:
        raise SpendCapReached()

    used_quota = db.scalar(
        select(func.count(AIUsage.id)).where(
            AIUsage.user_id == user.id,
            AIUsage.created_at >= today,
            AIUsage.paid_with == "quota",
            AIUsage.status.in_(["reserved", "done"]),
        )
    ) or 0
    limit = int(plan_limit(user, "ai_ops_per_day", now))  # type: ignore[call-overload]

    if used_quota < limit:
        paid_with = "quota"
    elif user.ai_credits > 0:
        user.ai_credits -= 1
        paid_with = "credits"
    else:
        raise QuotaExceeded()

    row = AIUsage(user_id=user.id, kind=kind, paid_with=paid_with, status="reserved", created_at=now)
    db.add(row)
    db.flush()
    return row


def settle_ai_op(
    db: Session,
    user: User,
    row: AIUsage,
    *,
    ok: bool,
    model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    if ok:
        row.status = "done"
        row.model = model
        row.input_tokens = input_tokens
        row.output_tokens = output_tokens
        row.cost_usd = _cost_usd(input_tokens, output_tokens)
    else:
        row.status = "failed"
        if row.paid_with == "credits":
            user.ai_credits += 1  # refund: the student got nothing
    db.commit()


def weekly_evaluations_used(db: Session, user: User, now: datetime | None = None) -> int:
    from .models import QuizSession

    now = now or utcnow()
    return db.scalar(
        select(func.count(QuizSession.id)).where(
            QuizSession.user_id == user.id,
            QuizSession.kind == "evaluation",
            QuizSession.created_at >= now - timedelta(days=7),
        )
    ) or 0
