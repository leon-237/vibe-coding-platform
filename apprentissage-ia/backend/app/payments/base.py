"""Payment provider interface. The app never trusts a webhook body on its own:
a webhook is only a signal, and the status is re-read from the provider API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol


@dataclass(frozen=True)
class ProviderTransaction:
    status: str  # "successful" | "failed" | "pending" (provider vocabulary, lowercased)
    amount: int
    currency: str
    provider_tx_id: str


class PaymentProvider(Protocol):
    name: str

    def create_checkout(
        self, *, tx_ref: str, amount: int, currency: str, email: str, redirect_url: str, title: str
    ) -> str:
        """Return the URL where the student completes the payment."""
        ...

    def verify_transaction(self, tx_ref: str) -> ProviderTransaction | None:
        """Server-to-server lookup of a transaction by our reference."""
        ...

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        ...
