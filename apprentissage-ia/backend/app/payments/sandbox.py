"""In-memory provider for local development and tests. Never used in production."""
from __future__ import annotations

import hashlib
import hmac
from typing import Mapping

from .base import ProviderTransaction

SIGNATURE_HEADER = "x-sandbox-signature"


class SandboxProvider:
    name = "sandbox"

    def __init__(self, secret: str = "sandbox-secret") -> None:
        self._secret = secret
        self.transactions: dict[str, ProviderTransaction] = {}

    def sign(self, body: bytes) -> str:
        return hmac.new(self._secret.encode(), body, hashlib.sha256).hexdigest()

    def create_checkout(
        self, *, tx_ref: str, amount: int, currency: str, email: str, redirect_url: str, title: str
    ) -> str:
        self.transactions[tx_ref] = ProviderTransaction("pending", amount, currency, f"sb-{tx_ref}")
        return f"https://sandbox.invalid/pay/{tx_ref}"

    def simulate_payment(self, tx_ref: str, status: str = "successful") -> None:
        tx = self.transactions[tx_ref]
        self.transactions[tx_ref] = ProviderTransaction(status, tx.amount, tx.currency, tx.provider_tx_id)

    def verify_transaction(self, tx_ref: str) -> ProviderTransaction | None:
        return self.transactions.get(tx_ref)

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        return hmac.compare_digest(headers.get(SIGNATURE_HEADER, ""), self.sign(body))
