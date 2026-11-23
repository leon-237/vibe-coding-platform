"""AI provider access. The server is the only place where the API key is used."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

import httpx

from ..config import get_settings


class AIError(Exception):
    """The AI provider failed or is not configured."""


@dataclass
class AIResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


class AIClient(Protocol):
    def complete(self, *, model: str, system: str, user: str, max_tokens: int = 1024) -> AIResult: ...


class AnthropicClient:
    """Minimal client for the Anthropic Messages API (no SDK dependency)."""

    def __init__(self, api_key: str, base_url: str, timeout: float = 60.0) -> None:
        self._api_key = api_key
        self._http = httpx.Client(base_url=base_url, timeout=timeout)

    def complete(self, *, model: str, system: str, user: str, max_tokens: int = 1024) -> AIResult:
        try:
            response = self._http.post(
                "/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
        except httpx.HTTPError as exc:
            raise AIError("Le fournisseur IA est injoignable") from exc
        if response.status_code >= 400:
            raise AIError(f"Le fournisseur IA a répondu HTTP {response.status_code}")
        data = response.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage") or {}
        return AIResult(
            text=text,
            model=data.get("model", model),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
        )


@dataclass
class FakeAIClient:
    """Deterministic client for tests and local demos. Records every call."""

    responder: Callable[[str, str], str] | None = None
    calls: list[tuple[str, str, str]] = field(default_factory=list)
    fail: bool = False

    def complete(self, *, model: str, system: str, user: str, max_tokens: int = 1024) -> AIResult:
        self.calls.append((model, system, user))
        if self.fail:
            raise AIError("panne simulée")
        text = self.responder(system, user) if self.responder else "Réponse de test."
        return AIResult(text=text, model=model, input_tokens=1000, output_tokens=200)


_override: AIClient | None = None


def set_ai_client(client: AIClient | None) -> None:
    """Inject a client (used by tests)."""
    global _override
    _override = client


def get_ai_client() -> AIClient:
    if _override is not None:
        return _override
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise AIError("ANTHROPIC_API_KEY n'est pas configurée")
    return AnthropicClient(settings.anthropic_api_key, settings.anthropic_base_url)
