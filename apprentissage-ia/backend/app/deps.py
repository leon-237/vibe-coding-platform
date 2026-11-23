from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .ai.client import AIError
from .db import get_db
from .models import User
from .quota import QuotaExceeded, SpendCapReached
from .security import decode_token


def get_current_user(
    authorization: str | None = Header(default=None), db: Session = Depends(get_db)
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Connexion requise")
    user_id = decode_token(authorization[len("Bearer "):])
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session invalide ou expirée")
    if user.is_suspended:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Compte suspendu")
    return user


def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à l'administration")
    return user


def ai_http_error(exc: Exception) -> HTTPException:
    """Translate AI-related domain errors into HTTP responses the app can show."""
    if isinstance(exc, QuotaExceeded):
        return HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Quota IA du jour atteint. Revenez demain, achetez des crédits ou passez à un abonnement.",
        )
    if isinstance(exc, SpendCapReached):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Service IA momentanément suspendu")
    if isinstance(exc, AIError):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    raise exc
