"""Ollama provider — default for local-first v0.4.0 narrative.

Talks to a local Ollama daemon over HTTP. ``httpx`` is the transport
and is declared in the ``llm`` extra rather than as a hard dep so
engine-only installs stay small. The import is lazy so this module is
safe to load even without the extra — the ``httpx`` requirement only
bites when a caller actually invokes ``generate`` or ``probe``.
"""

from __future__ import annotations

from typing import Any

from .provider import GenerationResult, LLMProvider, ProviderProbe

DEFAULT_ENDPOINT = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b-instruct"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_TIMEOUT_SECONDS = 120.0


class OllamaNotInstalledError(RuntimeError):
    """Raised when httpx is not available in the current environment."""


def _load_httpx():
    try:
        import httpx  # type: ignore
    except ImportError as e:
        raise OllamaNotInstalledError(
            "Ollama provider requires httpx. Install with "
            "'pip install clawmodeler-engine[llm]'."
        ) from e
    return httpx


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        endpoint: str = DEFAULT_ENDPOINT,
        temperature: float = DEFAULT_TEMPERATURE,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        *,
        http_client: Any = None,
    ) -> None:
        self.model = model
        self.endpoint = endpoint.rstrip("/")
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self._http_client = http_client

    def _client(self):
        if self._http_client is not None:
            return self._http_client
        return _load_httpx()

    def generate(
        self, prompt: str, facts: list[dict[str, Any]]
    ) -> GenerationResult:
        client = self._client()
        body = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        resp = client.post(
            f"{self.endpoint}/api/generate",
            json=body,
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        return GenerationResult(
            text=data.get("response", ""),
            provider=self.name,
            model=self.model,
            metadata={
                "endpoint": self.endpoint,
                "temperature": self.temperature,
                "eval_count": data.get("eval_count"),
                "eval_duration_ns": data.get("eval_duration"),
            },
        )

    def probe(self) -> ProviderProbe:
        try:
            client = self._client()
        except OllamaNotInstalledError as e:
            return ProviderProbe(
                ok=False,
                detail=str(e),
                provider=self.name,
                model=self.model,
            )
        try:
            resp = client.get(f"{self.endpoint}/api/tags", timeout=5.0)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            return ProviderProbe(
                ok=False,
                detail=f"ollama unreachable at {self.endpoint}: {e}",
                provider=self.name,
                model=self.model,
            )
        installed = [m.get("name", "") for m in payload.get("models", [])]
        model_installed = self.model in installed
        detail = (
            f"ollama reachable at {self.endpoint}; "
            f"{len(installed)} models installed; "
            f"requested model '{self.model}' "
            f"{'is' if model_installed else 'is NOT'} installed"
        )
        return ProviderProbe(
            ok=True,
            detail=detail,
            provider=self.name,
            model=self.model,
            metadata={
                "endpoint": self.endpoint,
                "installed_models": installed,
                "model_installed": model_installed,
            },
        )

    @property
    def is_cloud(self) -> bool:
        return False
