"""Billing rules. A subscription or credit pack is granted only when the provider
confirms a successful transaction with the same amount and currency as ours."""
from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from ..catalog import PRODUCTS, get_country, price_for
from ..config import get_settings
from ..models import Payment, PromoCode, User, utcnow
from ..payments.base import PaymentProvider

log = logging.getLogger("billing")


class BillingError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _validate_promo(db: Session, code: str | None, amount: int) -> tuple[int, str | None]:
    if not code:
        return 0, None
    promo = db.get(PromoCode, code.strip().upper())
    now = utcnow()
    if (
        promo is None
        or not promo.active
        or (promo.expires_at and promo.expires_at < now)
        or (promo.max_uses is not None and promo.uses >= promo.max_uses)
    ):
        raise BillingError("Code promo invalide ou expiré", 422)
    return amount * promo.percent_off // 100, promo.code


def create_payment(
    db: Session, user: User, product: str, promo_code: str | None, provider: PaymentProvider
) -> tuple[Payment, str]:
    if product not in PRODUCTS:
        raise BillingError("Produit inconnu", 422)
    country = get_country(user.country)
    gross = price_for(country.code, product)
    discount, promo = _validate_promo(db, promo_code, gross)
    amount = gross - discount

    tx_ref = f"aia-{user.id}-{secrets.token_hex(8)}"
    link = provider.create_checkout(
        tx_ref=tx_ref,
        amount=amount,
        currency=country.currency,
        email=user.email,
        redirect_url=f"{get_settings().public_app_url}/billing/return",
        title=f"Application d'apprentissage IA – {product}",
    )
    payment = Payment(
        user_id=user.id,
        tx_ref=tx_ref,
        product=product,
        amount=amount,
        discount=discount,
        currency=country.currency,
        country=country.code,
        provider=provider.name,
        promo_code=promo,
        status="pending",
    )
    db.add(payment)
    db.commit()
    return payment, link


def apply_payment(db: Session, payment: Payment) -> None:
    """Grant the product once. Calling it twice has no extra effect."""
    if payment.status == "succeeded":
        return
    user = db.get(User, payment.user_id)
    assert user is not None
    spec = PRODUCTS[payment.product]
    now = utcnow()
    if spec["kind"] == "plan":
        base = user.plan_expires_at if user.plan_expires_at and user.plan_expires_at > now else now
        user.plan = str(spec["plan"])
        user.plan_expires_at = base + timedelta(days=int(spec["days"]))  # type: ignore[arg-type]
    else:
        user.ai_credits += int(spec["credits"])  # type: ignore[arg-type]
    if payment.promo_code:
        promo = db.get(PromoCode, payment.promo_code)
        if promo is not None:
            promo.uses += 1
    payment.status = "succeeded"
    payment.paid_at = now
    db.commit()


def reconcile(db: Session, payment: Payment, provider: PaymentProvider) -> str:
    """Ask the provider for the real status of this payment and act on it."""
    if payment.status != "pending":
        return payment.status
    tx = provider.verify_transaction(payment.tx_ref)
    if tx is None:
        return payment.status
    payment.provider_tx_id = tx.provider_tx_id
    if tx.status == "successful":
        if tx.amount != payment.amount or tx.currency != payment.currency:
            payment.status = "failed"
            db.commit()
            log.error("amount mismatch on %s: expected %s %s, got %s %s",
                      payment.tx_ref, payment.amount, payment.currency, tx.amount, tx.currency)
            return payment.status
        apply_payment(db, payment)
    elif tx.status in {"failed", "cancelled", "error"}:
        payment.status = "failed"
        db.commit()
    return payment.status
