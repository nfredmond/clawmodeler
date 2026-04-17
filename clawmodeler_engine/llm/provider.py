"""LLM provider interface for AI-generated narrative.

A provider turns ``(prompt, facts)`` into prose. The prose is then
handed to :func:`clawmodeler_engine.llm.grounding.validate_and_ground`
— the deterministic validator is the single source of truth for
whether a sentence is allowed to ship. Providers never self-certify
their own output.

This module only defines the interface and a ``FakeProvider`` for
tests. Concrete providers (``ollama``, ``anthropic``, ``openai``) live
in sibling modules so their optional SDKs can stay lazy-imported.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GenerationResult:
    text: str
    provider: str
    model: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderProbe:
    ok: bool
    detail: str
    provider: str
    model: str
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    name: str = ""

    @abstractmethod
    def generate(
        self, prompt: str, facts: list[dict[str, Any]]
    ) -> GenerationResult: ...

    @abstractmethod
    def probe(self) -> ProviderProbe: ...

    @property
    @abstractmethod
    def is_cloud(self) -> bool: ...


class FakeProvider(LLMProvider):
    """Deterministic provider for tests and demos.

    Returns whatever ``canned_text`` it was initialized with, tagged
    with a made-up model name. ``is_cloud`` is always False so the
    confidentiality warning stays quiet.
    """

    name = "fake"

    def __init__(
        self, canned_text: str = "", model: str = "fake-model-v1"
    ) -> None:
        self._text = canned_text
        self._model = model
        self.calls: list[tuple[str, list[dict[str, Any]]]] = []

    def generate(
        self, prompt: str, facts: list[dict[str, Any]]
    ) -> GenerationResult:
        self.calls.append((prompt, list(facts)))
        return GenerationResult(
            text=self._text, provider=self.name, model=self._model
        )

    def probe(self) -> ProviderProbe:
        return ProviderProbe(
            ok=True,
            detail="fake provider (in-process, no network)",
            provider=self.name,
            model=self._model,
        )

    @property
    def is_cloud(self) -> bool:
        return False
