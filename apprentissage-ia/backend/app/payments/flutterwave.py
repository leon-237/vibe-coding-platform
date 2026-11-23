"""Flutterwave (v3) adapter: hosted checkout with Mobile Money and cards.

Endpoints and headers follow Flutterwave's v3 public API. They must be checked
against the sandbox with real test keys before go-live (not done here: no keys).
"""
from __future__ import annotations

import hmac
from typing import Mapping

import httpx

from .base import ProviderTransaction


class FlutterwaveProvider:
    name = "flutterwave"

    def __init__(self, secret_key: str, webhook_hash: str, base_url: str, timeout: float = 30.0) -> None:
        self._secret_key = secret_key
        self._webhook_hash = webhook_hash
        self._http = httpx.Client(base_url=base_url, timeout=timeout)

    @property
    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._secret_key}"}

    def create_checkout(
        self, *, tx_ref: str, amount: int, currency: str, email: str, redirect_url: str, title: str
    ) -> str:
        response = self._http.post(
            "/payments",
            headers=self._auth,
            json={
                "tx_ref": tx_ref,
                "amount": amount,
                "currency": currency,
                "redirect_url": redirect_url,
                "customer": {"email": email},
                "customizations": {"title": title},
            },
        )
        response.raise_for_status()
        return response.json()["data"]["link"]

    def verify_transaction(self, tx_ref: str) -> ProviderTransaction | None:
        response = self._http.get(
            "/transactions/verify_by_reference", headers=self._auth, params={"tx_ref": tx_ref}
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json().get("data") or {}
        return ProviderTransaction(
            status=str(data.get("status", "")).lower(),
            amount=int(float(data.get("amount", 0))),
            currency=str(data.get("currency", "")).upper(),
            provider_tx_id=str(data.get("id", "")),
        )

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        # Flutterwave sends the secret hash configured on the dashboard in "verif-hash".
        if not self._webhook_hash:
            return False
        received = headers.get("verif-hash", "")
        return hmac.compare_digest(received, self._webhook_hash)
