"""OpenAI BYOK provider.

Cloud provider. ``is_cloud`` is True — the CLI must surface a
confidentiality warning before any call goes out. The ``openai`` SDK
is a lazy optional dependency, declared in the ``llm-cloud`` extra.
"""

from __future__ import annotations

import os
from typing import Any

from .provider import GenerationResult, LLMProvider, ProviderProbe

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 2048


class OpenAINotInstalledError(RuntimeError):
    """Raised when the openai SDK is not available."""


class OpenAIMissingKeyError(RuntimeError):
    """Raised when no OPENAI_API_KEY is resolvable."""


def _load_sdk():
    try:
        import openai as _sdk  # type: ignore
    except ImportError as e:
        raise OpenAINotInstalledError(
            "OpenAI provider requires the 'openai' SDK. Install with "
            "'pip install clawmodeler-engine[llm-cloud]'."
        ) from e
    return _sdk


def _resolve_api_key(explicit: str | None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("OPENAI_API_KEY", "").strip()
    if env:
        return env
    raise OpenAIMissingKeyError(
        "OPENAI_API_KEY is not set. Run `clawmodeler-engine llm "
        "configure api_key=...` or export the env var."
    )


class OpenAIProvider(LLMProvider):
    name = "openai"

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
        return sdk.OpenAI(api_key=_resolve_api_key(self._explicit_key))

    def generate(
        self, prompt: str, facts: list[dict[str, Any]]
    ) -> GenerationResult:
        client = self._sdk_client()
        response = client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        choice = response.choices[0]
        text = choice.message.content or ""
        return GenerationResult(
            text=text,
            provider=self.name,
            model=self.model,
            metadata={
                "finish_reason": getattr(choice, "finish_reason", None),
                "prompt_tokens": getattr(
                    getattr(response, "usage", None), "prompt_tokens", None
                ),
                "completion_tokens": getattr(
                    getattr(response, "usage", None), "completion_tokens", None
                ),
            },
        )

    def probe(self) -> ProviderProbe:
        try:
            _load_sdk()
        except OpenAINotInstalledError as e:
            return ProviderProbe(
                ok=False, detail=str(e), provider=self.name, model=self.model
            )
        try:
            _resolve_api_key(self._explicit_key)
        except OpenAIMissingKeyError as e:
            return ProviderProbe(
                ok=False, detail=str(e), provider=self.name, model=self.model
            )
        return ProviderProbe(
            ok=True,
            detail=(
                f"openai SDK present and OPENAI_API_KEY resolved; "
                f"model '{self.model}' will be used on next generate call"
            ),
            provider=self.name,
            model=self.model,
            metadata={"cloud": True},
        )

    @property
    def is_cloud(self) -> bool:
        return True
