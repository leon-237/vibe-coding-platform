from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..catalog import COUNTRIES, PLAN_LIMITS, PRODUCTS, get_country, price_for
from ..db import get_db
from ..deps import get_current_user
from ..models import Payment, User, utcnow
from ..payments import get_payment_provider
from ..quota import effective_plan, weekly_evaluations_used
from ..services.billing import BillingError, create_payment, reconcile

router = APIRouter(tags=["billing"])


class CheckoutIn(BaseModel):
    product: Literal["etudiant_monthly", "etudiant_annual", "premium_monthly", "credits_100", "credits_300"]
    promo_code: str | None = Field(default=None, max_length=40)


@router.get("/billing/catalog")
def catalog(country: str | None = None, user: User = Depends(get_current_user)) -> dict:
    code = (country or user.country).upper()
    if code not in COUNTRIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pays non pris en charge")
    currency = get_country(code).currency
    return {
        "country": code,
        "currency": currency,
        "products": [
            {
                "code": name,
                "kind": spec["kind"],
                "price": price_for(code, name),
                "plan": spec.get("plan"),
                "days": spec.get("days"),
                "credits": spec.get("credits"),
            }
            for name, spec in PRODUCTS.items()
        ],
        "plans": PLAN_LIMITS,
        "countries": [{"code": c.code, "name": c.name, "currency": c.currency} for c in COUNTRIES.values()],
    }


@router.post("/billing/checkout", status_code=status.HTTP_201_CREATED)
def checkout(body: CheckoutIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        payment, link = create_payment(db, user, body.product, body.promo_code, get_payment_provider())
    except BillingError as exc:
        raise HTTPException(exc.status_code, str(exc))
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    return {
        "tx_ref": payment.tx_ref,
        "product": payment.product,
        "amount": payment.amount,
        "discount": payment.discount,
        "currency": payment.currency,
        "payment_link": link,
    }


@router.get("/billing/payments/{tx_ref}")
def payment_status(tx_ref: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    payment = db.scalar(select(Payment).where(Payment.tx_ref == tx_ref, Payment.user_id == user.id))
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paiement introuvable")
    if payment.status == "pending":
        try:
            reconcile(db, payment, get_payment_provider(payment.provider))
        except RuntimeError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    db.refresh(user)
    return {"tx_ref": payment.tx_ref, "status": payment.status, "subscription": subscription_out(user)}


@router.post("/billing/webhooks/{provider_name}")
async def webhook(provider_name: str, request: Request, db: Session = Depends(get_db)) -> dict:
    """Provider notification. It only triggers a re-check; the status is read back from the provider."""
    body = await request.body()
    try:
        provider = get_payment_provider(provider_name)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    if not provider.verify_webhook(request.headers, body):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Signature invalide")
    try:
        tx_ref = json.loads(body).get("data", {}).get("tx_ref")
    except (ValueError, AttributeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Corps invalide")
    if not tx_ref:
        return {"ignored": True}
    payment = db.scalar(select(Payment).where(Payment.tx_ref == tx_ref))
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paiement inconnu")
    return {"status": reconcile(db, payment, provider)}


def subscription_out(user: User) -> dict:
    plan = effective_plan(user, utcnow())
    return {
        "plan": plan,
        "expires_at": user.plan_expires_at if plan != "free" else None,
        "ai_credits": user.ai_credits,
        "limits": PLAN_LIMITS[plan],
    }


@router.get("/billing/subscription")
def subscription(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    data = subscription_out(user)
    data["evaluations_this_week"] = weekly_evaluations_used(db, user)
    return data
