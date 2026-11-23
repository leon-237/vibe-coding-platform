from __future__ import annotations

import random
from collections import defaultdict

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.client import AIError
from ..db import get_db
from ..deps import ai_http_error, get_current_user
from ..models import Attempt, Chapter, Exercise, QuizSession, ReviewItem, Subject, User, utcnow
from ..quota import QuotaExceeded, SpendCapReached, plan_limit, weekly_evaluations_used
from ..services.quiz import (
    XP_CORRECT,
    XP_CORRECT_EVALUATION,
    XP_WRONG,
    flag_for_review,
    level_for,
    schedule_review,
    touch_streak,
)
from ..services.tutor import ChapterNotFound, chapter_for_user, explain, generate_qcm

router = APIRouter(tags=["learning"])


class GenerateIn(BaseModel):
    count: int = Field(default=5, ge=1, le=10)
    difficulty: Literal["facile", "moyen", "difficile"] = "moyen"


class QuizIn(BaseModel):
    kind: Literal["quiz", "evaluation"] = "quiz"
    subject_id: int | None = None
    chapter_id: int | None = None
    count: int = Field(default=10, ge=1, le=20)


class AnswerItem(BaseModel):
    exercise_id: int
    choice: int | None = Field(default=None, ge=0, le=3)


class SubmitIn(BaseModel):
    answers: list[AnswerItem]


class ReviewAnswerIn(BaseModel):
    choice: int = Field(ge=0, le=3)


class ExplainIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    subject_id: int | None = None
    chapter_id: int | None = None


def _public_question(ex: Exercise) -> dict:
    """What the client receives before answering: never the answer index."""
    return {"id": ex.id, "question": ex.question, "choices": ex.choices, "difficulty": ex.difficulty}


def _owned_exercises_query(user: User, subject_id: int | None, chapter_id: int | None):
    stmt = (
        select(Exercise)
        .join(Chapter, Exercise.chapter_id == Chapter.id)
        .join(Subject, Chapter.subject_id == Subject.id)
        .where(Subject.user_id == user.id, Exercise.owner_id == user.id)
    )
    if chapter_id is not None:
        stmt = stmt.where(Chapter.id == chapter_id)
    if subject_id is not None:
        stmt = stmt.where(Subject.id == subject_id)
    return stmt


def _attempt_counts(db: Session, user: User) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    for exercise_id in db.scalars(select(Attempt.exercise_id).where(Attempt.user_id == user.id)).all():
        counts[exercise_id] += 1
    return counts


# --- Question generation ------------------------------------------------------

@router.post("/chapters/{chapter_id}/exercises/generate", status_code=status.HTTP_201_CREATED)
def generate(
    chapter_id: int,
    body: GenerateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        chapter = chapter_for_user(db, user, chapter_id)
    except ChapterNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chapitre introuvable")
    try:
        created = generate_qcm(db, user, chapter, body.count, body.difficulty)
    except (QuotaExceeded, SpendCapReached, AIError) as exc:
        raise ai_http_error(exc)
    return {"created": len(created), "exercise_ids": [e.id for e in created]}


# --- Quiz and evaluations -------------------------------------------------------

@router.post("/quizzes", status_code=status.HTTP_201_CREATED)
def start_quiz(body: QuizIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if body.subject_id is None and body.chapter_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Indiquez une matière ou un chapitre")

    if body.kind == "evaluation":
        limit = int(plan_limit(user, "evaluations_per_week"))  # type: ignore[call-overload]
        if weekly_evaluations_used(db, user) >= limit:
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                f"Limite de {limit} évaluation(s) par semaine atteinte pour votre formule.",
            )

    candidates = list(db.scalars(_owned_exercises_query(user, body.subject_id, body.chapter_id)).all())
    if not candidates:
        raise HTTPException(status.HTTP_409_CONFLICT, "Aucune question disponible : générez des QCM d'abord")

    # Least-seen questions first, random among equals.
    counts = _attempt_counts(db, user)
    random.shuffle(candidates)
    candidates.sort(key=lambda ex: counts.get(ex.id, 0))
    chosen = candidates[: body.count]

    session = QuizSession(
        user_id=user.id,
        kind=body.kind,
        subject_id=body.subject_id,
        chapter_id=body.chapter_id,
        exercise_ids=[ex.id for ex in chosen],
        total=len(chosen),
        status="open",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {
        "session_id": session.id,
        "kind": session.kind,
        "questions": [_public_question(ex) for ex in chosen],
    }


@router.post("/quizzes/{session_id}/submit")
def submit_quiz(
    session_id: int, body: SubmitIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    session = db.get(QuizSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session introuvable")
    if session.status == "submitted":
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette session a déjà été corrigée")

    answers = {a.exercise_id: a.choice for a in body.answers}
    unknown = set(answers) - set(session.exercise_ids)
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Question absente de cette session")

    now = utcnow()
    exercises = {e.id: e for e in db.scalars(select(Exercise).where(Exercise.id.in_(session.exercise_ids))).all()}
    results = []
    correct_count = 0
    xp_gained = 0
    for exercise_id in session.exercise_ids:
        exercise = exercises[exercise_id]
        chosen = answers.get(exercise_id)
        is_correct = chosen is not None and chosen == exercise.answer_index
        db.add(Attempt(
            user_id=user.id, exercise_id=exercise_id, session_id=session.id,
            chosen_index=chosen, is_correct=is_correct, source=session.kind, created_at=now,
        ))
        if is_correct:
            correct_count += 1
            xp_gained += XP_CORRECT_EVALUATION if session.kind == "evaluation" else XP_CORRECT
        else:
            xp_gained += XP_WRONG
            flag_for_review(db, user, exercise_id, now)
        results.append({
            "exercise_id": exercise_id,
            "question": exercise.question,
            "choices": exercise.choices,
            "chosen_index": chosen,
            "correct_index": exercise.answer_index,
            "is_correct": is_correct,
            "explanation": exercise.explanation,
        })

    session.correct = correct_count
    session.status = "submitted"
    session.submitted_at = now
    user.xp += xp_gained
    touch_streak(user, now.date())
    db.commit()
    return {
        "session_id": session.id,
        "kind": session.kind,
        "total": session.total,
        "correct": correct_count,
        "score_percent": round(100 * correct_count / session.total) if session.total else 0,
        "xp_gained": xp_gained,
        "results": results,
    }


@router.get("/quizzes")
def quiz_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    sessions = db.scalars(
        select(QuizSession)
        .where(QuizSession.user_id == user.id, QuizSession.status == "submitted")
        .order_by(QuizSession.submitted_at.desc())
        .limit(50)
    ).all()
    return [
        {
            "session_id": s.id,
            "kind": s.kind,
            "submitted_at": s.submitted_at,
            "total": s.total,
            "correct": s.correct,
            "score_percent": round(100 * s.correct / s.total) if s.total else 0,
        }
        for s in sessions
    ]


# --- Spaced repetition -----------------------------------------------------------

@router.get("/reviews/due")
def due_reviews(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    now = utcnow()
    items = db.execute(
        select(ReviewItem, Exercise)
        .join(Exercise, ReviewItem.exercise_id == Exercise.id)
        .where(ReviewItem.user_id == user.id, ReviewItem.due_at <= now)
        .order_by(ReviewItem.due_at)
        .limit(20)
    ).all()
    return {
        "questions": [_public_question(ex) for _item, ex in items],
        "due_count": len(items),
    }


@router.post("/reviews/{exercise_id}/answer")
def answer_review(
    exercise_id: int,
    body: ReviewAnswerIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    exercise = db.get(Exercise, exercise_id)
    if exercise is None or exercise.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question introuvable")
    if db.scalar(select(ReviewItem.id).where(ReviewItem.user_id == user.id, ReviewItem.exercise_id == exercise_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cette question n'est pas à réviser")

    now = utcnow()
    is_correct = body.choice == exercise.answer_index
    db.add(Attempt(
        user_id=user.id, exercise_id=exercise_id, session_id=None,
        chosen_index=body.choice, is_correct=is_correct, source="review", created_at=now,
    ))
    item = schedule_review(db, user, exercise_id, is_correct, now)
    user.xp += XP_CORRECT if is_correct else XP_WRONG
    touch_streak(user, now.date())
    db.commit()
    return {
        "is_correct": is_correct,
        "correct_index": exercise.answer_index,
        "explanation": exercise.explanation,
        "next_review_at": item.due_at,
        "interval_days": item.interval_days,
    }


# --- AI tutor ------------------------------------------------------------------

@router.post("/ai/explain")
def ai_explain(body: ExplainIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        answer, chunk_ids, cached = explain(db, user, body.question, body.subject_id, body.chapter_id)
    except (QuotaExceeded, SpendCapReached, AIError) as exc:
        raise ai_http_error(exc)
    return {"answer": answer, "source_chunk_ids": chunk_ids, "cached": cached}


# --- Dashboard -------------------------------------------------------------------

@router.get("/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    now = utcnow()
    subjects = db.scalars(select(Subject).where(Subject.user_id == user.id).order_by(Subject.name)).all()
    exercises = db.scalars(
        select(Exercise).join(Chapter).join(Subject)
        .where(Subject.user_id == user.id, Exercise.owner_id == user.id)
    ).all()
    chapter_of = {ex.id: ex.chapter_id for ex in exercises}
    attempts = db.scalars(select(Attempt).where(Attempt.user_id == user.id)).all()

    per_chapter: dict[int, list[bool]] = defaultdict(list)
    for a in attempts:
        if a.exercise_id in chapter_of:
            per_chapter[chapter_of[a.exercise_id]].append(a.is_correct)

    subject_stats = []
    for subject in subjects:
        chapter_ids = {c.id for c in subject.chapters}
        questions = sum(1 for ex in exercises if ex.chapter_id in chapter_ids)
        outcomes = [r for cid in chapter_ids for r in per_chapter.get(cid, [])]
        attempted_ids = {a.exercise_id for a in attempts
                         if chapter_of.get(a.exercise_id) in chapter_ids}
        subject_stats.append({
            "subject_id": subject.id,
            "name": subject.name,
            "questions": questions,
            "covered_percent": round(100 * len(attempted_ids) / questions) if questions else 0,
            "accuracy_percent": round(100 * sum(outcomes) / len(outcomes)) if outcomes else None,
        })

    chapter_titles = {c.id: c.title for s in subjects for c in s.chapters}
    weakest = sorted(
        (
            {"chapter_id": cid, "title": chapter_titles.get(cid, ""),
             "accuracy_percent": round(100 * sum(v) / len(v)), "attempts": len(v)}
            for cid, v in per_chapter.items() if len(v) >= 3
        ),
        key=lambda row: row["accuracy_percent"],
    )[:3]

    due_count = db.query(ReviewItem).filter(ReviewItem.user_id == user.id, ReviewItem.due_at <= now).count()
    recent = db.scalars(
        select(QuizSession).where(QuizSession.user_id == user.id, QuizSession.status == "submitted")
        .order_by(QuizSession.submitted_at.desc()).limit(5)
    ).all()

    return {
        "xp": user.xp,
        "gamification_level": level_for(user.xp),
        "xp_to_next_level": 100 - (user.xp % 100),
        "streak_days": user.streak_days,
        "due_reviews": due_count,
        "subjects": subject_stats,
        "weakest_chapters": weakest,
        "recent_sessions": [
            {"session_id": s.id, "kind": s.kind, "submitted_at": s.submitted_at,
             "score_percent": round(100 * s.correct / s.total) if s.total else 0}
            for s in recent
        ],
        "recommendation": _recommend(weakest, due_count),
    }


def _recommend(weakest: list[dict], due_count: int) -> str:
    if due_count:
        return f"Vous avez {due_count} question(s) à réviser aujourd'hui."
    if weakest:
        return f"Travaillez le chapitre « {weakest[0]['title']} » (précision {weakest[0]['accuracy_percent']} %)."
    return "Lancez un quiz pour que nous puissions cibler vos révisions."
