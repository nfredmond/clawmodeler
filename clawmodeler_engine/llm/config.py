"""Workspace-level LLM configuration and provider factory.

``llm_config.json`` lives at the workspace root and is seeded by
``clawmodeler-engine init``. The file is plain JSON so planners can
inspect and edit it by hand; the ``llm configure`` CLI is a
convenience.

Confidentiality posture: the default (ollama) keeps every byte on the
machine. Switching to anthropic/openai is a deliberate act — the
config records it, and ``llm doctor`` surfaces a loud warning before
any cloud call.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .anthropic import (
    DEFAULT_MODEL as ANTHROPIC_DEFAULT_MODEL,
)
from .anthropic import (
    AnthropicProvider,
)
from .grounding import GroundingMode
from .ollama import (
    DEFAULT_ENDPOINT as OLLAMA_DEFAULT_ENDPOINT,
)
from .ollama import (
    DEFAULT_MODEL as OLLAMA_DEFAULT_MODEL,
)
from .ollama import (
    DEFAULT_TEMPERATURE as OLLAMA_DEFAULT_TEMPERATURE,
)
from .ollama import (
    OllamaProvider,
)
from .openai import (
    DEFAULT_MODEL as OPENAI_DEFAULT_MODEL,
)
from .openai import (
    OpenAIProvider,
)
from .provider import LLMProvider

CONFIG_FILENAME = "llm_config.json"
SUPPORTED_PROVIDERS = ("ollama", "anthropic", "openai", "fake")
CLOUD_PROVIDERS = frozenset({"anthropic", "openai"})


class LLMConfigError(ValueError):
    """Raised when an llm config is invalid or an update cannot apply."""


@dataclass
class LLMConfig:
    provider: str = "ollama"
    model: str = OLLAMA_DEFAULT_MODEL
    endpoint: str = OLLAMA_DEFAULT_ENDPOINT
    temperature: float = OLLAMA_DEFAULT_TEMPERATURE
    grounding_mode: str = GroundingMode.STRICT.value
    max_tokens: int = 2048
    cloud_confirmed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LLMConfig":
        allowed = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in allowed}
        cfg = cls(**filtered)
        _validate(cfg)
        return cfg


def default_config() -> LLMConfig:
    return LLMConfig()


def config_path(workspace: Path) -> Path:
    return Path(workspace) / CONFIG_FILENAME


def load_config(workspace: Path) -> LLMConfig:
    path = config_path(workspace)
    if not path.exists():
        return default_config()
    data = json.loads(path.read_text(encoding="utf-8"))
    return LLMConfig.from_dict(data)


def save_config(workspace: Path, config: LLMConfig) -> Path:
    _validate(config)
    path = config_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _validate(cfg: LLMConfig) -> None:
    if cfg.provider not in SUPPORTED_PROVIDERS:
        raise LLMConfigError(
            f"provider must be one of {SUPPORTED_PROVIDERS}; got {cfg.provider!r}"
        )
    try:
        GroundingMode(cfg.grounding_mode)
    except ValueError as e:
        raise LLMConfigError(
            f"grounding_mode must be one of "
            f"{[m.value for m in GroundingMode]}; got {cfg.grounding_mode!r}"
        ) from e
    if not isinstance(cfg.temperature, (int, float)):
        raise LLMConfigError("temperature must be a number")
    if not 0.0 <= float(cfg.temperature) <= 2.0:
        raise LLMConfigError("temperature must be between 0.0 and 2.0")
    if not isinstance(cfg.max_tokens, int) or cfg.max_tokens <= 0:
        raise LLMConfigError("max_tokens must be a positive integer")


def apply_updates(config: LLMConfig, updates: dict[str, str]) -> LLMConfig:
    """Return a new config with ``updates`` merged in.

    Values come in as strings (from the CLI ``key=value`` surface) and
    are coerced to the dataclass field types. Unknown keys raise.
    """

    coerced: dict[str, object] = {}
    for key, raw in updates.items():
        if key not in LLMConfig.__dataclass_fields__:
            raise LLMConfigError(
                f"unknown config key {key!r}; "
                f"supported: {sorted(LLMConfig.__dataclass_fields__)}"
            )
        field = LLMConfig.__dataclass_fields__[key]
        coerced[key] = _coerce(field.type, key, raw)

    defaults_for_provider_switch: dict[str, object] = {}
    if "provider" in coerced and coerced["provider"] != config.provider:
        defaults_for_provider_switch = _provider_defaults(str(coerced["provider"]))

    merged = {**defaults_for_provider_switch, **coerced}

    # Any config change resets cloud_confirmed unless the update is exactly
    # cloud_confirmed=true. This prevents a stale confirm from carrying over
    # across provider changes.
    if "cloud_confirmed" not in merged:
        merged["cloud_confirmed"] = False

    new_cfg = replace(config, **merged)
    _validate(new_cfg)
    return new_cfg


def _coerce(annotation, key: str, raw: str) -> object:
    ann = str(annotation)
    if "bool" in ann:
        lowered = raw.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
        raise LLMConfigError(f"{key}: expected true/false, got {raw!r}")
    if "int" in ann and "float" not in ann:
        try:
            return int(raw)
        except ValueError as e:
            raise LLMConfigError(f"{key}: expected integer, got {raw!r}") from e
    if "float" in ann:
        try:
            return float(raw)
        except ValueError as e:
            raise LLMConfigError(f"{key}: expected number, got {raw!r}") from e
    return raw


def _provider_defaults(provider: str) -> dict[str, object]:
    if provider == "ollama":
        return {
            "model": OLLAMA_DEFAULT_MODEL,
            "endpoint": OLLAMA_DEFAULT_ENDPOINT,
        }
    if provider == "anthropic":
        return {
            "model": ANTHROPIC_DEFAULT_MODEL,
            "endpoint": "",
        }
    if provider == "openai":
        return {
            "model": OPENAI_DEFAULT_MODEL,
            "endpoint": "",
        }
    return {}


def build_provider(config: LLMConfig) -> LLMProvider:
    """Instantiate the ``LLMProvider`` described by ``config``."""

    if config.provider == "ollama":
        return OllamaProvider(
            model=config.model,
            endpoint=config.endpoint or OLLAMA_DEFAULT_ENDPOINT,
            temperature=config.temperature,
        )
    if config.provider == "anthropic":
        return AnthropicProvider(
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
    if config.provider == "openai":
        return OpenAIProvider(
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
    raise LLMConfigError(f"cannot build provider for {config.provider!r}")


def parse_key_value_pairs(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise LLMConfigError(
                f"expected key=value, got {pair!r}"
            )
        key, _, value = pair.partition("=")
        key = key.strip()
        if not key:
            raise LLMConfigError(f"empty key in {pair!r}")
        out[key] = value
    return out
