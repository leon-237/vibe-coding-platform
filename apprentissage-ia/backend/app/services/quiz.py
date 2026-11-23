"""QCM parsing (AI output is untrusted), SM-2 spaced repetition, XP and streaks."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..models import ReviewItem, User


class QCMItem(BaseModel):
    question: str = Field(min_length=5, max_length=1000)
    choices: list[str] = Field(min_length=4, max_length=4)
    answer_index: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=3, max_length=2000)
    difficulty: str = "moyen"

    @field_validator("question", "explanation", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("choices")
    @classmethod
    def _choices_valid(cls, choices: list[str]) -> list[str]:
        cleaned = [c.strip() for c in choices]
        if any(not c for c in cleaned) or len(set(cleaned)) != 4:
            raise ValueError("choix vides ou en double")
        return cleaned

    @field_validator("difficulty")
    @classmethod
    def _difficulty(cls, value: str) -> str:
        return value if value in {"facile", "moyen", "difficile"} else "moyen"


def parse_qcm(raw: str) -> list[QCMItem]:
    """Extract the JSON object from the model output and keep only valid questions."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    items: list[QCMItem] = []
    for entry in data.get("questions", []) if isinstance(data, dict) else []:
        try:
            items.append(QCMItem.model_validate(entry))
        except Exception:  # invalid question: dropped rather than shown to a student
            continue
    return items


# --- SM-2 -------------------------------------------------------------------

MIN_EASE = 1.3


def sm2_next(ease: float, interval: int, repetitions: int, correct: bool) -> tuple[float, int, int]:
    """Return (ease, interval_days, repetitions) after one answer (SM-2 with q=4 or q=1)."""
    quality = 4 if correct else 1
    ease = max(MIN_EASE, ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
    if quality < 3:
        return ease, 1, 0
    repetitions += 1
    if repetitions == 1:
        interval = 1
    elif repetitions == 2:
        interval = 6
    else:
        interval = max(1, round(interval * ease))
    return ease, interval, repetitions


def schedule_review(
    db: Session, user: User, exercise_id: int, correct: bool, now: datetime
) -> ReviewItem:
    """Called after a review answer: applies SM-2."""
    item = db.query(ReviewItem).filter_by(user_id=user.id, exercise_id=exercise_id).one()
    item.ease, item.interval_days, item.repetitions = sm2_next(
        item.ease, item.interval_days, item.repetitions, correct
    )
    item.due_at = now + timedelta(days=item.interval_days)
    return item


def flag_for_review(db: Session, user: User, exercise_id: int, now: datetime) -> None:
    """Called when a quiz answer is wrong: the question comes back right away."""
    item = db.query(ReviewItem).filter_by(user_id=user.id, exercise_id=exercise_id).one_or_none()
    if item is None:
        db.add(ReviewItem(user_id=user.id, exercise_id=exercise_id, due_at=now))
    else:
        item.repetitions = 0
        item.due_at = now


# --- Gamification ------------------------------------------------------------

XP_CORRECT = 10
XP_CORRECT_EVALUATION = 15
XP_WRONG = 2


def level_for(xp: int) -> int:
    return xp // 100 + 1


def touch_streak(user: User, today) -> None:
    """Consecutive days with at least one answer keep the streak alive."""
    if user.last_active_date == today:
        return
    if user.last_active_date == today - timedelta(days=1):
        user.streak_days += 1
    else:
        user.streak_days = 1
    user.last_active_date = today
