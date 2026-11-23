"""AI tutor: answers a question using the student's own course extracts.

Retrieval is keyword overlap (no embeddings yet). Identical question + identical
extracts are served from cache, which costs no quota and no provider call.
"""
from __future__ import annotations

import hashlib
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.client import AIError, get_ai_client
from ..ai.prompts import analysis_prompt, explain_prompt, qcm_prompt
from ..config import get_settings
from ..models import AICache, Chapter, DocumentChunk, Exercise, Subject, User, utcnow
from ..quota import reserve_ai_op, settle_ai_op
from .quiz import parse_qcm

_WORD = re.compile(r"[a-zà-ÿ0-9]{3,}")
_MAX_CHUNKS_SCANNED = 800


class ChapterNotFound(Exception):
    pass


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def retrieve_chunks(
    db: Session, user: User, query: str, subject_id: int | None, chapter_id: int | None, k: int = 4
) -> list[DocumentChunk]:
    stmt = select(DocumentChunk).where(DocumentChunk.user_id == user.id)
    if chapter_id is not None:
        stmt = stmt.where(DocumentChunk.chapter_id == chapter_id)
    elif subject_id is not None:
        stmt = stmt.where(DocumentChunk.subject_id == subject_id)
    chunks = db.scalars(stmt.limit(_MAX_CHUNKS_SCANNED)).all()
    wanted = _tokens(query)
    scored = [(len(wanted & _tokens(c.text)), c) for c in chunks]
    scored = [pair for pair in scored if pair[0] > 0]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [chunk for _, chunk in scored[:k]]


def _cache_key(language: str, model: str, question: str, chunks: list[DocumentChunk]) -> str:
    raw = "|".join([language, model, question.strip().lower(), *(str(c.id) for c in chunks)])
    return hashlib.sha256(raw.encode()).hexdigest()


def explain(
    db: Session, user: User, question: str, subject_id: int | None, chapter_id: int | None
) -> tuple[str, list[int], bool]:
    """Return (answer, chunk_ids_used, served_from_cache)."""
    settings = get_settings()
    chunks = retrieve_chunks(db, user, question, subject_id, chapter_id)
    model = settings.model_simple
    key = _cache_key(user.language, model, question, chunks)

    cached = db.get(AICache, key)
    if cached is not None:
        return cached.text, [c.id for c in chunks], True

    system, prompt = explain_prompt(user.language, question, [c.text for c in chunks])
    op = reserve_ai_op(db, user, "explain")
    try:
        result = get_ai_client().complete(model=model, system=system, user=prompt, max_tokens=900)
    except AIError:
        settle_ai_op(db, user, op, ok=False)
        raise
    settle_ai_op(
        db, user, op, ok=True, model=result.model,
        input_tokens=result.input_tokens, output_tokens=result.output_tokens,
    )
    db.add(AICache(key=key, text=result.text, created_at=utcnow()))
    db.commit()
    return result.text, [c.id for c in chunks], False


def chapter_for_user(db: Session, user: User, chapter_id: int) -> Chapter:
    chapter = db.get(Chapter, chapter_id)
    if chapter is None or db.get(Subject, chapter.subject_id).user_id != user.id:  # type: ignore[union-attr]
        raise ChapterNotFound()
    return chapter


def generate_qcm(
    db: Session, user: User, chapter: Chapter, count: int, difficulty: str
) -> list[Exercise]:
    subject = db.get(Subject, chapter.subject_id)
    assert subject is not None
    chunks = retrieve_chunks(db, user, chapter.title, subject.id, chapter.id, k=6)
    context = "\n\n".join(c.text for c in chunks)
    if not context and chapter.notions:
        context = chapter.notions
    context = context[:8000]

    model = get_settings().model_simple
    system, prompt = qcm_prompt(user.language, subject.name, chapter.title, context, count, difficulty)
    op = reserve_ai_op(db, user, "generate_qcm")
    try:
        result = get_ai_client().complete(model=model, system=system, user=prompt, max_tokens=3000)
    except AIError:
        settle_ai_op(db, user, op, ok=False)
        raise
    settle_ai_op(
        db, user, op, ok=True, model=result.model,
        input_tokens=result.input_tokens, output_tokens=result.output_tokens,
    )

    created: list[Exercise] = []
    for item in parse_qcm(result.text)[:count]:
        exercise = Exercise(
            chapter_id=chapter.id,
            owner_id=user.id,
            question=item.question,
            choices=item.choices,
            answer_index=item.answer_index,
            explanation=item.explanation,
            difficulty=item.difficulty,
            validated=False,
        )
        db.add(exercise)
        created.append(exercise)
    db.commit()
    return created


def analyze_document(db: Session, user: User, document_id: int) -> str:
    from ..models import Document

    document = db.get(Document, document_id)
    if document is None or document.user_id != user.id:
        raise ChapterNotFound()
    text = "\n".join(c.text for c in document.chunks)[:20000]
    model = get_settings().model_complex
    system, prompt = analysis_prompt(user.language, text)
    op = reserve_ai_op(db, user, "analyze_document")
    try:
        result = get_ai_client().complete(model=model, system=system, user=prompt, max_tokens=2500)
    except AIError:
        settle_ai_op(db, user, op, ok=False)
        raise
    settle_ai_op(
        db, user, op, ok=True, model=result.model,
        input_tokens=result.input_tokens, output_tokens=result.output_tokens,
    )
    return result.text
