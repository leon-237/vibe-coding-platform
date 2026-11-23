from __future__ import annotations

from ..config import get_settings
from .base import PaymentProvider
from .flutterwave import FlutterwaveProvider
from .sandbox import SandboxProvider

_override: PaymentProvider | None = None
_sandbox = SandboxProvider()


def set_payment_provider(provider: PaymentProvider | None) -> None:
    global _override
    _override = provider


def get_payment_provider(name: str = "flutterwave") -> PaymentProvider:
    if _override is not None:
        return _override
    if name == "sandbox":
        return _sandbox
    settings = get_settings()
    if not settings.flutterwave_secret_key:
        raise RuntimeError("FLW_SECRET_KEY n'est pas configurée")
    return FlutterwaveProvider(
        settings.flutterwave_secret_key,
        settings.flutterwave_webhook_hash or "",
        settings.flutterwave_base_url,
    )
