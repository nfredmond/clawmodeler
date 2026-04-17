"""Anthropic (Claude) BYOK provider.

Cloud provider. ``is_cloud`` is True — the CLI must surface a
confidentiality warning before any call goes out. The ``anthropic``
SDK is a lazy optional dependency, declared in the ``llm-cloud``
extra. Importing this module does not pull in the SDK; only
``generate`` and ``probe`` do.

API key resolution order:

1. explicit ``api_key`` constructor argument (tests, integration code)
2. ``ANTHROPIC_API_KEY`` environment variable
"""

from __future__ import annotations

import os
from typing import Any

from .provider import GenerationResult, LLMProvider, ProviderProbe

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 2048


class AnthropicNotInstalledError(RuntimeError):
    """Raised when the anthropic SDK is not available."""


class AnthropicMissingKeyError(RuntimeError):
    """Raised when no ANTHROPIC_API_KEY is resolvable."""


def _load_sdk():
    try:
        import anthropic as _sdk  # type: ignore
    except ImportError as e:
        raise AnthropicNotInstalledError(
            "Anthropic provider requires the 'anthropic' SDK. Install "
            "with 'pip install clawmodeler-engine[llm-cloud]'."
        ) from e
    return _sdk


def _resolve_api_key(explicit: str | None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if env:
        return env
    raise AnthropicMissingKeyError(
        "ANTHROPIC_API_KEY is not set. Run `clawmodeler-engine llm "
        "configure api_key=...` or export the env var."
    )


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        *,
        client: Any = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._explicit_key = api_key
        self._client = client

    def _sdk_client(self):
        if self._client is not None:
            return self._client
        sdk = _load_sdk()
        return sdk.Anthropic(api_key=_resolve_api_key(self._explicit_key))

    def generate(
        self, prompt: str, facts: list[dict[str, Any]]
    ) -> GenerationResult:
        client = self._sdk_client()
        message = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in message.content if getattr(block, "text", None)
        )
        return GenerationResult(
            text=text,
            provider=self.name,
            model=self.model,
            metadata={
                "stop_reason": getattr(message, "stop_reason", None),
                "input_tokens": getattr(
                    getattr(message, "usage", None), "input_tokens", None
                ),
                "output_tokens": getattr(
                    getattr(message, "usage", None), "output_tokens", None
                ),
            },
        )

    def probe(self) -> ProviderProbe:
        try:
            _load_sdk()
        except AnthropicNotInstalledError as e:
            return ProviderProbe(
                ok=False, detail=str(e), provider=self.name, model=self.model
            )
        try:
            _resolve_api_key(self._explicit_key)
        except AnthropicMissingKeyError as e:
            return ProviderProbe(
                ok=False, detail=str(e), provider=self.name, model=self.model
            )
        return ProviderProbe(
            ok=True,
            detail=(
                f"anthropic SDK present and ANTHROPIC_API_KEY resolved; "
                f"model '{self.model}' will be used on next generate call"
            ),
            provider=self.name,
            model=self.model,
            metadata={"cloud": True},
        )

    @property
    def is_cloud(self) -> bool:
        return True
