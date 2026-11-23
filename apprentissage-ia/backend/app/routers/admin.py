from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import get_admin_user
from ..models import AIUsage, Payment, PromoCode, User, utcnow

router = APIRouter(prefix="/admin", tags=["admin"])


class SuspendIn(BaseModel):
    suspended: bool


class PromoIn(BaseModel):
    code: str = Field(min_length=3, max_length=40)
    percent_off: int = Field(ge=1, le=100)
    max_uses: int | None = Field(default=None, ge=1)
    days_valid: int | None = Field(default=None, ge=1, le=3650)


@router.get("/summary")
def summary(days: int = 30, _admin: User = Depends(get_admin_user), db: Session = Depends(get_db)) -> dict:
    since = utcnow() - timedelta(days=days)
    settings = get_settings()

    users_by_plan = dict(db.execute(select(User.plan, func.count(User.id)).group_by(User.plan)).all())
    revenue = [
        {"currency": currency, "amount": int(total), "payments": int(count)}
        for currency, total, count in db.execute(
            select(Payment.currency, func.sum(Payment.amount), func.count(Payment.id))
            .where(Payment.status == "succeeded", Payment.paid_at >= since)
            .group_by(Payment.currency)
        ).all()
    ]
    ai_ops, ai_cost_usd = db.execute(
        select(func.count(AIUsage.id), func.coalesce(func.sum(AIUsage.cost_usd), 0.0)).where(
            AIUsage.status == "done", AIUsage.created_at >= since
        )
    ).one()
    ai_cost_fcfa = ai_cost_usd * settings.fcfa_per_usd
    # Revenue is in FCFA for every country we serve (XAF and XOF are both pegged to the euro).
    revenue_fcfa = sum(r["amount"] for r in revenue)
    return {
        "window_days": days,
        "users_by_plan": users_by_plan,
        "revenue": revenue,
        "ai": {
            "operations": int(ai_ops),
            "cost_usd": round(float(ai_cost_usd), 4),
            "cost_per_operation_fcfa": round(ai_cost_fcfa / ai_ops, 2) if ai_ops else 0,
        },
        "estimated_margin_before_fees_fcfa": round(revenue_fcfa - ai_cost_fcfa),
        "note": "La marge n'inclut pas les commissions de paiement, des stores, l'hébergement ni le marketing.",
    }


@router.get("/users")
def list_users(
    limit: int = 50, offset: int = 0, _admin: User = Depends(get_admin_user), db: Session = Depends(get_db)
) -> list[dict]:
    users = db.scalars(select(User).order_by(User.id).limit(min(limit, 200)).offset(offset)).all()
    return [
        {"id": u.id, "email": u.email, "country": u.country, "plan": u.plan,
         "plan_expires_at": u.plan_expires_at, "is_suspended": u.is_suspended, "created_at": u.created_at}
        for u in users
    ]


@router.post("/users/{user_id}/suspend")
def suspend(user_id: int, body: SuspendIn, _admin: User = Depends(get_admin_user), db: Session = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable")
    user.is_suspended = body.suspended
    db.commit()
    return {"id": user.id, "is_suspended": user.is_suspended}


@router.post("/promo-codes", status_code=status.HTTP_201_CREATED)
def create_promo(body: PromoIn, _admin: User = Depends(get_admin_user), db: Session = Depends(get_db)) -> dict:
    code = body.code.strip().upper()
    if db.get(PromoCode, code) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Code déjà existant")
    expires = utcnow() + timedelta(days=body.days_valid) if body.days_valid else None
    db.add(PromoCode(code=code, percent_off=body.percent_off, max_uses=body.max_uses, expires_at=expires))
    db.commit()
    return {"code": code, "percent_off": body.percent_off, "expires_at": expires}
