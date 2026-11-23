from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai.client import AIError
from ..config import get_settings
from ..db import get_db
from ..deps import ai_http_error, get_current_user
from ..models import Chapter, Document, DocumentChunk, Subject, User
from ..quota import QuotaExceeded, SpendCapReached, plan_limit
from ..services.documents import EmptyDocument, UnsupportedFile, chunk_text, extract_text
from ..services.tutor import ChapterNotFound, analyze_document

router = APIRouter(tags=["content"])


class SubjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    semester: int | None = Field(default=None, ge=1, le=12)


class ChapterIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    position: int = Field(default=0, ge=0, le=999)
    notions: str | None = Field(default=None, max_length=5000)


def _own_subject(db: Session, user: User, subject_id: int) -> Subject:
    subject = db.get(Subject, subject_id)
    if subject is None or subject.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Matière introuvable")
    return subject


def _own_chapter(db: Session, user: User, chapter_id: int) -> Chapter:
    chapter = db.get(Chapter, chapter_id)
    if chapter is None or db.get(Subject, chapter.subject_id).user_id != user.id:  # type: ignore[union-attr]
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chapitre introuvable")
    return chapter


def _subject_out(subject: Subject, with_chapters: bool = False) -> dict:
    data = {"id": subject.id, "name": subject.name, "semester": subject.semester}
    if with_chapters:
        data["chapters"] = [
            {"id": c.id, "title": c.title, "position": c.position, "notions": c.notions}
            for c in subject.chapters
        ]
    else:
        data["chapter_count"] = len(subject.chapters)
    return data


@router.post("/subjects", status_code=status.HTTP_201_CREATED)
def create_subject(
    body: SubjectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    limit = plan_limit(user, "max_subjects")
    if limit is not None:
        count = db.scalar(select(func.count(Subject.id)).where(Subject.user_id == user.id)) or 0
        if count >= int(limit):  # type: ignore[call-overload]
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                f"Limite de {limit} matières atteinte pour votre formule. Passez à l'abonnement Étudiant.",
            )
    subject = Subject(user_id=user.id, name=body.name, semester=body.semester)
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return _subject_out(subject)


@router.get("/subjects")
def list_subjects(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    subjects = db.scalars(
        select(Subject).where(Subject.user_id == user.id).order_by(Subject.semester, Subject.name)
    ).all()
    return [_subject_out(s) for s in subjects]


@router.get("/subjects/{subject_id}")
def get_subject(subject_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return _subject_out(_own_subject(db, user, subject_id), with_chapters=True)


@router.delete("/subjects/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(subject_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    db.delete(_own_subject(db, user, subject_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/subjects/{subject_id}/chapters", status_code=status.HTTP_201_CREATED)
def create_chapter(
    subject_id: int, body: ChapterIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    _own_subject(db, user, subject_id)
    chapter = Chapter(subject_id=subject_id, title=body.title, position=body.position, notions=body.notions)
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return {"id": chapter.id, "title": chapter.title, "position": chapter.position, "notions": chapter.notions}


@router.delete("/chapters/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chapter(chapter_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    db.delete(_own_chapter(db, user, chapter_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    subject_id: int = Form(...),
    chapter_id: int | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _own_subject(db, user, subject_id)
    if chapter_id is not None:
        chapter = _own_chapter(db, user, chapter_id)
        if chapter.subject_id != subject_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Le chapitre n'appartient pas à la matière")

    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Fichier trop volumineux")
    filename = (file.filename or "document").split("/")[-1][:255]
    try:
        text = extract_text(filename, data)
    except UnsupportedFile as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except EmptyDocument as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    document = Document(
        user_id=user.id, subject_id=subject_id, chapter_id=chapter_id,
        filename=filename, char_count=len(text),
    )
    for position, piece in enumerate(chunk_text(text)):
        document.chunks.append(
            DocumentChunk(
                user_id=user.id, subject_id=subject_id, chapter_id=chapter_id,
                position=position, text=piece,
            )
        )
    db.add(document)
    db.commit()
    db.refresh(document)
    return {"id": document.id, "filename": document.filename, "chunks": len(document.chunks)}


@router.get("/documents")
def list_documents(
    subject_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[dict]:
    stmt = select(Document).where(Document.user_id == user.id)
    if subject_id is not None:
        stmt = stmt.where(Document.subject_id == subject_id)
    return [
        {"id": d.id, "filename": d.filename, "subject_id": d.subject_id, "chapter_id": d.chapter_id,
         "char_count": d.char_count}
        for d in db.scalars(stmt.order_by(Document.created_at.desc())).all()
    ]


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    document = db.get(Document, document_id)
    if document is None or document.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document introuvable")
    db.delete(document)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/documents/{document_id}/analyze")
def analyze(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if not plan_limit(user, "document_analysis"):
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            "L'analyse de documents est réservée à la formule Premium.",
        )
    try:
        text = analyze_document(db, user, document_id)
    except ChapterNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document introuvable")
    except (QuotaExceeded, SpendCapReached, AIError) as exc:
        raise ai_http_error(exc)
    return {"analysis": text}
