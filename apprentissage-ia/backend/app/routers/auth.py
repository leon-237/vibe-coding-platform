from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..catalog import COUNTRIES
from ..db import get_db
from ..deps import get_current_user
from ..models import (
    AIUsage,
    Attempt,
    Chapter,
    Document,
    DocumentChunk,
    Exercise,
    Payment,
    QuizSession,
    ReviewItem,
    Subject,
    User,
)
from ..quota import effective_plan
from ..security import create_token, hash_password, verify_password

router = APIRouter(tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=2, max_length=2)
    language: Literal["fr", "en"] = "fr"
    establishment: str | None = Field(default=None, max_length=200)
    level: str | None = Field(default=None, max_length=100)
    filiere: str | None = Field(default=None, max_length=100)
    specialite: str | None = Field(default=None, max_length=100)
    academic_year: str | None = Field(default=None, max_length=20)

    @field_validator("country")
    @classmethod
    def _country(cls, value: str) -> str:
        code = value.upper()
        if code not in COUNTRIES:
            raise ValueError(f"pays non pris en charge (choisir parmi {', '.join(COUNTRIES)})")
        return code


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ProfileUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    language: Literal["fr", "en"] | None = None
    establishment: str | None = Field(default=None, max_length=200)
    level: str | None = Field(default=None, max_length=100)
    filiere: str | None = Field(default=None, max_length=100)
    specialite: str | None = Field(default=None, max_length=100)
    academic_year: str | None = Field(default=None, max_length=20)

    @field_validator("country")
    @classmethod
    def _country(cls, value: str | None) -> str | None:
        if value is None:
            return None
        code = value.upper()
        if code not in COUNTRIES:
            raise ValueError("pays non pris en charge")
        return code


class DeleteAccountIn(BaseModel):
    password: str


PROFILE_FIELDS = (
    "first_name", "last_name", "country", "language",
    "establishment", "level", "filiere", "specialite", "academic_year",
)


def user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "country": user.country,
        "language": user.language,
        "establishment": user.establishment,
        "level": user.level,
        "filiere": user.filiere,
        "specialite": user.specialite,
        "academic_year": user.academic_year,
        "plan": effective_plan(user),
        "plan_expires_at": user.plan_expires_at,
        "ai_credits": user.ai_credits,
        "xp": user.xp,
        "streak_days": user.streak_days,
        "is_admin": user.is_admin,
    }


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> dict:
    email = str(body.email).lower()
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Un compte existe déjà avec cet e-mail")
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        **{f: getattr(body, f) for f in PROFILE_FIELDS if f != "country"},
        country=body.country,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"access_token": create_token(user.id), "user": user_out(user)}


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.email == str(body.email).lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou mot de passe incorrect")
    if user.is_suspended:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Compte suspendu")
    return {"access_token": create_token(user.id), "user": user_out(user)}


@router.get("/countries")
def countries() -> list[dict]:
    """Public list used by the registration form."""
    return [{"code": c.code, "name": c.name, "currency": c.currency} for c in COUNTRIES.values()]


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return user_out(user)


@router.patch("/me")
def update_me(
    body: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None and field in {"first_name", "last_name", "country", "language"}:
            continue
        setattr(user, field, value)
    db.commit()
    return user_out(user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    body: DeleteAccountIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Permanently delete the account and all personal data (right to erasure)."""
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Mot de passe incorrect")
    uid = user.id
    db.execute(delete(Attempt).where(Attempt.user_id == uid))
    db.execute(delete(ReviewItem).where(ReviewItem.user_id == uid))
    db.execute(delete(QuizSession).where(QuizSession.user_id == uid))
    db.execute(delete(DocumentChunk).where(DocumentChunk.user_id == uid))
    db.execute(delete(Document).where(Document.user_id == uid))
    db.execute(delete(Exercise).where(Exercise.owner_id == uid))
    subject_ids = db.scalars(select(Subject.id).where(Subject.user_id == uid)).all()
    if subject_ids:
        db.execute(delete(Chapter).where(Chapter.subject_id.in_(subject_ids)))
    db.execute(delete(Subject).where(Subject.user_id == uid))
    db.execute(delete(Payment).where(Payment.user_id == uid))
    db.execute(delete(AIUsage).where(AIUsage.user_id == uid))
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
